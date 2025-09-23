import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import Pool
from django.urls import reverse
from rest_framework.test import APIClient
from user.models import Seller, SellerAccount
from credit.models import Credit, Transaction
from django.db.models import Sum
import uuid


@pytest.fixture
def test_seller_start_up():
    seller = Seller.objects.create_user(username="seller_1", password="password")
    account = SellerAccount.objects.create(seller=seller, phone_number="09111111111")
    admin = Seller.objects.create_superuser(username="admin", password="admin")
    return seller, account, admin


@pytest.mark.django_db
def test_not_unique_idempotency_must_fail(test_seller_start_up):
    seller, _, admin = test_seller_start_up
    credit = Credit.objects.create(seller=seller, amount=123)
    
    client = APIClient()
    client.force_authenticate(user=admin)
    url_change = reverse("change_credit_status", args=[credit.id])
    
    client.patch(url_change, {"status": "approved"}, HTTP_IDEMPOTENCY_KEY="not_unique")
    response = client.patch(url_change, {"status": "approved"}, HTTP_IDEMPOTENCY_KEY="not_unique")
    
    assert response.status_code == 429

@pytest.mark.django_db
def test_simple_credit_and_sales_balance_check(test_seller_start_up):
    seller, account, admin = test_seller_start_up
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
def test_parallel_sales_balance_check(total_balance, amount, request_number, test_seller_start_up):
    seller, account, _ = test_seller_start_up
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

    client.force_authenticate(user=seller)
    url_charge = reverse("charge_phone")

    def make_charge_request(number: int):
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
    
    
def process_worker(args):
    seller_username, phone_number, amount, index = args
    from rest_framework.test import APIClient
    from user.models import Seller

    client = APIClient()
    user = Seller.objects.get(username=seller_username)
    client.force_authenticate(user=user)
    url_charge = "/api/v1/credit/account/charge/"  # or use reverse if accessible
    response = client.post(
        url_charge,
        {"phone_number": phone_number, "amount": amount},
        HTTP_IDEMPOTENCY_KEY=f"{uuid.uuid4()}_{index}_{uuid.uuid4()}"
    )
    return response.status_code

# @pytest.mark.django_db(transaction=True)
# @pytest.mark.parametrize(
#     "total_balance, amount, request_number",
#     [
#         (100_000, 500, 100),
#         (50_000, 1000, 50),
#         (200_000, 2000, 120),
#     ]
# )
# def test_parallel_sales_processes(total_balance, amount, request_number):
#     from user.models import Seller, SellerAccount
#     from credit.models import Transaction
#     from django.db.models import Sum
#     from multiprocessing import Pool
#     import uuid

#     seller = Seller.objects.create_user(username="process_seller", password="test1234")
#     account = SellerAccount.objects.create(seller=seller, phone_number="09444444444")
#     seller.total_balance = total_balance
#     seller.save()

#     # prepare args for each request
#     args_list = [(seller.username, account.phone_number, amount, i) for i in range(request_number)]

#     with Pool(processes=10) as pool:
#         results = pool.map(process_worker, args_list)

#     seller.refresh_from_db()
#     account.refresh_from_db()

#     successful_sales = Transaction.objects.filter(seller=seller, type=Transaction.Type.SALE).aggregate(
#         total=Sum('change')
#     )['total'] or 0

#     assert seller.total_balance == total_balance - successful_sales
#     assert account.balance == successful_sales

#     # Ensure idempotency keys are unique
#     assert Transaction.objects.filter(seller=seller, type=Transaction.Type.SALE).count() == len(set(
#         t.idempotency for t in Transaction.objects.filter(seller=seller, type=Transaction.Type.SALE)
#     ))

#     if (total_balance, amount, request_number) in [(100_000, 500, 100), (50_000, 1000, 50)]:
#         assert all(r in (200,) for r in results)
#     else:
#         assert all(r in (200, 409) for r in results)