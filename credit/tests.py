import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.urls import reverse
from rest_framework.test import APIClient
from user.models import Seller, SellerAccount
from credit.models import Credit, Transaction
from django.db.models import Sum
from django.db import close_old_connections
import uuid


@pytest.fixture
def base_seller_data():
    seller = Seller.objects.create_user(username="seller_1", password="password")
    account = SellerAccount.objects.create(seller=seller, phone_number="09111111111")
    admin = Seller.objects.create_superuser(username="admin", password="admin")
    return seller, account, admin


@pytest.mark.django_db
def test_not_unique_idempotency_must_fail(base_seller_data):
    seller, _, admin = base_seller_data
    credit = Credit.objects.create(seller=seller, amount=123)
    
    client = APIClient()
    client.force_authenticate(user=admin)
    url_change = reverse("change_credit_status", args=[credit.id])
    
    client.patch(url_change, {"status": "approved"}, HTTP_IDEMPOTENCY_KEY="not_unique")
    response = client.patch(url_change, {"status": "approved"}, HTTP_IDEMPOTENCY_KEY="not_unique")
    
    assert response.status_code == 429

@pytest.mark.django_db
def test_simple_credit_and_sales_balance_check(base_seller_data):
    seller, account, admin = base_seller_data
    client = APIClient()

    client.force_authenticate(user=seller)
    url_credit = reverse("create_credit")
    response = client.post(url_credit, {"amount": 1_000_000})
    assert response.status_code == 201
    credit_id = response.data["id"]

    client.force_authenticate(user=admin)
    url_change = reverse("change_credit_status", args=[credit_id])
    response = client.patch(url_change, {"status": "approved"}, HTTP_IDEMPOTENCY_KEY="unique_number")
    assert response.status_code == 200

    seller.refresh_from_db()
    assert seller.total_balance == 1_000_000

    client.force_authenticate(user=seller)
    url_charge = reverse("charge_phone")
    for number in range(60):
        response = client.post(
            url_charge,
            {"phone_number": "09111111111", "amount": 5000},
            HTTP_IDEMPOTENCY_KEY=f"{uuid.uuid4()}_{number}",
        )
        assert response.status_code == 200

    seller.refresh_from_db()
    account.refresh_from_db()
    assert seller.total_balance == 1_000_000 - (60 * 5000)  # 700000
    assert account.balance == (60 * 5000)
    
    # check total balance from trancation
    assert Transaction.objects.filter(seller=seller).count() == 61  # one increase with 60 deacreace
    
    # Ensure idempotency keys are unique
    assert Transaction.objects.filter(seller=seller, type=Transaction.Type.SALE).count() == len(set(
        t.idempotency for t in Transaction.objects.filter(seller=seller, type=Transaction.Type.SALE)
    ))
    
    
    increase_sum = Transaction.objects.filter(seller=seller, type=Transaction.Type.INCREASE).aggregate(total=Sum('change'))['total'] 
    sell_sum = Transaction.objects.filter(seller=seller, type=Transaction.Type.SALE).aggregate(total=Sum('change'))['total'] 
    assert seller.total_balance == increase_sum - sell_sum
    

@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "total_balance, amount, request_number",
    [
        (100_000, 500, 100), # less than balance
        (50_000, 1000, 50), # equal to balance
        (200_000, 2000, 120), # more than balance
    ]
)
def test_parallel_sales_balance_check(total_balance, amount, request_number, base_seller_data):
    seller, account, _ = base_seller_data
    client = APIClient()

    Credit.objects.create(seller=seller, amount=amount, status=Credit.Status.APPROVED)
    Transaction.objects.create(
        seller=seller,
        account=account,
        change=total_balance,
        type=Transaction.Type.INCREASE,
        idempotency="some_random_number",
        balance_before=0,
        balance_after=total_balance
    )
    
    seller.total_balance = total_balance
    seller.save()

    url_charge = reverse("charge_phone")

    def make_charge_request(number: int):
        close_old_connections()
        client = APIClient()
        client.force_authenticate(user=seller)
        response = client.post(
            url_charge,
            {"phone_number": account.phone_number, "amount": amount},
            HTTP_IDEMPOTENCY_KEY=f"{uuid.uuid4()}_{number}"
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(make_charge_request, i) for i in range(request_number)]
        results = [f.result() for f in as_completed(futures)]

    seller.refresh_from_db()
    account.refresh_from_db()
    balance = total_balance - (amount * request_number)
    if balance < 0:
        balance = 0

    # Check balances
    increase_sum = Transaction.objects.filter(seller=seller, type=Transaction.Type.INCREASE).aggregate(total=Sum("change"))["total"] 
    sell_sum = Transaction.objects.filter(seller=seller, type=Transaction.Type.SALE).aggregate(total=Sum("change"))["total"] 
    assert seller.total_balance == increase_sum - sell_sum
    assert account.balance == sell_sum
    assert seller.total_balance == balance
    

    # Ensure idempotency keys are unique
    assert Transaction.objects.filter(seller=seller, type=Transaction.Type.SALE).count() == len(set(
        t.idempotency for t in Transaction.objects.filter(seller=seller, type=Transaction.Type.SALE)
    ))
    
    
    if (total_balance, amount, request_number) == (100_000, 500, 100) or (total_balance, amount, request_number) == (50_000, 1000, 50):
        assert all(r in (200,) for r in results)
    else:
        assert all(r in (200, 409) for r in results)
    
    
    
@pytest.mark.django_db(transaction=True)
def test_2_parallel_sales_balance_check(base_seller_data):
    seller1, account1, _ = base_seller_data

    seller2 = Seller.objects.create_user(
        username="seller2",
        password="password123",
        total_balance=0,
    )
    account2 = seller2.accounts.create(phone_number="09120000002")

    seller_params = [
        (seller1, account1, 100_000, 500, 100),  # seller1
        (seller2, account2, 50_000, 1000, 50),   # seller2
    ]

    url_charge = reverse("charge_phone")

    def setup_seller(seller, account, total_balance, amount):
        Credit.objects.create(seller=seller, amount=amount, status=Credit.Status.APPROVED)
        Transaction.objects.create(
            seller=seller,
            account=account,
            change=total_balance,
            type=Transaction.Type.INCREASE,
            idempotency=f"init_{seller.id}",
            balance_before=0,
            balance_after=total_balance,
        )
        seller.total_balance = total_balance
        seller.save()

    def make_charge_request(seller, account, amount, number):
        close_old_connections()
        client = APIClient()
        client.force_authenticate(user=seller)
        return client.post(
            url_charge,
            {"phone_number": account.phone_number, "amount": amount},
            HTTP_IDEMPOTENCY_KEY=f"{uuid.uuid4()}_{seller.id}_{number}",
        ).status_code

    # Setup both sellers
    for seller, account, total_balance, amount, _ in seller_params:
        setup_seller(seller, account, total_balance, amount)

    with ThreadPoolExecutor(max_workers=40) as executor:
        futures = []
        for seller, account, total_balance, amount, request_number in seller_params:
            for i in range(request_number):
                futures.append(executor.submit(make_charge_request, seller, account, amount, i))
        results = [f.result() for f in as_completed(futures)]

    for seller, account, total_balance, amount, request_number in seller_params:
        seller.refresh_from_db()
        account.refresh_from_db()

        expected_balance = total_balance - (amount * request_number)
        if expected_balance < 0:
            expected_balance = 0

        increase_sum = Transaction.objects.filter(
            seller=seller, type=Transaction.Type.INCREASE
        ).aggregate(total=Sum("change"))["total"]
        sell_sum = Transaction.objects.filter(
            seller=seller, type=Transaction.Type.SALE
        ).aggregate(total=Sum("change"))["total"]

        assert seller.total_balance == increase_sum - sell_sum
        assert account.balance == sell_sum
        assert seller.total_balance == expected_balance

        # Ensure idempotency keys are unique
        sales = Transaction.objects.filter(seller=seller, type=Transaction.Type.SALE)
        assert sales.count() == len(set(s.idempotency for s in sales))

    # For seller1 and seller2 together → expect mix of 200 / 409 depending on balance exhaustion
    assert all(r in (200, 409) for r in results)
    
    
