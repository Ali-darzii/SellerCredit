from django.db import transaction
from django.db.models import F
from rest_framework.generics import CreateAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from utils.idempotency import idempotency_key

from credit.models import Credit, Transaction
from credit.serializers import ChangeCreditStatusSerializer, ChargePhoneSerializer, CreateCreditSerializer, CreditSerializer
from user.models import Seller, SellerAccount
from utils.responses import ErrorResponses


class ChargePhoneView(APIView):
    permission_classes = (IsAuthenticated,)
    
    @idempotency_key(timeout=15)
    def post(self, request):
        serializer = ChargePhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data["phone_number"]
        amount = serializer.validated_data["amount"]
        idempotency = request.META["HTTP_IDEMPOTENCY_KEY"]
        
        with transaction.atomic():
            account = SellerAccount.objects.select_for_update().get(phone_number=phone_number)
            seller = Seller.objects.select_for_update().get(pk=account.seller_id)
            
            Transaction.objects.create(
                account=account,
                seller=None,
                change=amount,
                type=Transaction.Type.SALE,
                idempotency=idempotency,
                balance_before=seller.total_balance,
                balance_after=seller.total_balance - amount,
            )
            if seller.total_balance < amount:
                return Response(data={"detail":"There is not enough balance."}, status=status.HTTP_409_CONFLICT)
            
            seller.total_balance = F("total_balance") - amount
            seller.save(update_fields=["total_balance"])
            
            account.balance = F("balance") + amount
            account.save(update_fields=["balance"])
            return Response(data={"detail":"Transaction was successfull."})