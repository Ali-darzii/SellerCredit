import logging

from django.db import transaction
from django.db.models import F
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from utils.idempotency import idempotency_key
from utils.responses import ErrorResponses

from credit.models import Transaction
from credit.serializers import ChargePhoneSerializer
from user.models import Seller, SellerAccount

logger = logging.getLogger("django")

class ChargePhoneView(APIView):
    permission_classes = (IsAuthenticated,)
    
    @idempotency_key(timeout=15)
    def post(self, request):
        serializer = ChargePhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data["phone_number"]
        amount = serializer.validated_data["amount"]
        idempotency = request.META["HTTP_IDEMPOTENCY_KEY"]
        user = self.request.user
        
        with transaction.atomic():
            try:
                account = SellerAccount.objects.select_for_update().get(phone_number=phone_number)
                seller = Seller.objects.select_for_update().get(pk=account.seller_id)
                
                if user.id != seller.id:
                    logger.info(f"permission denied in `ChargePhone` for seller_id--{user.id}")
                    return Response(data=ErrorResponses.PERMISSION_DENIED, status=status.HTTP_403_FORBIDDEN)    
                
                
                if seller.total_balance < amount:
                    logger.info(f"not enough balance in `ChargePhone` for seller_id--{seller.id}")
                    return Response(data={"detail":"There is not enough balance."}, status=status.HTTP_409_CONFLICT)
                
                Transaction.objects.create(
                    account=account,
                    seller=seller,
                    change=amount,
                    type=Transaction.Type.SALE,
                    idempotency=idempotency,
                    balance_before=seller.total_balance,
                    balance_after=seller.total_balance - amount,
                )
                
                seller.total_balance = F("total_balance") - amount
                seller.save(update_fields=["total_balance"])
                
                account.balance = F("balance") + amount
                account.save(update_fields=["balance"])
                logger.info(f"`ChargePhone` amount--{amount} for seller_id--{seller.id} was successfull.")
                return Response(data={"detail":"Transaction was successfull."})
            
            except (SellerAccount.DoesNotExist, Seller.DoesNotExist):
                logger.warning(f"ERROR in `ChargePhone` a query didn't exist. \n {e}")
                return Response(ErrorResponses.OBJECT_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
            
            except Exception as e:
                logger.critical(f"ERROR in `ChargePhone` with seller_id--{seller.id}. \n {e}")
                return Response(data=ErrorResponses.SOMTHING_WENT_WRONG, status=status.HTTP_500_INTERNAL_SERVER_ERROR)