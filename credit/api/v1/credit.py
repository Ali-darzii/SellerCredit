import logging

from django.db import transaction
from django.db.models import F
from rest_framework.generics import CreateAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from utils.idempotency import idempotency_key

from credit.models import Credit, Transaction
from credit.serializers import ChangeCreditStatusSerializer, CreateCreditSerializer, CreditSerializer
from user.models import Seller, SellerAccount
from utils.responses import ErrorResponses

logger = logging.getLogger("django")

class CreateCreditView(CreateAPIView):
    serializer_class = CreateCreditSerializer
    permission_classes = (IsAuthenticated,)
    
    def perform_create(self, serializer):
        serializer.save(seller=self.request.user)
    

class ChangeCreditStatusView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    @idempotency_key(timeout=15)
    def patch(self, request, credit_id: int):
        serializer = ChangeCreditStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        idempotency = request.META["HTTP_IDEMPOTENCY_KEY"]
        
        with transaction.atomic():
            try:
                credit = Credit.objects.select_for_update().get(pk=credit_id)
                if credit.status == Credit.Status.APPROVED:
                    logger.info(f"repetitive approve status in `ChangeCreditStatus` with admin_id--{self.request.user.id}, for credit_id--{credit.id}")
                    return Response(
                        {"detail": "status is already approved"},
                        status=status.HTTP_200_OK,
                    )

                if data["status"] == Credit.Status.REJECTED:
                    logger.info(f"rejected status in `ChangeCreditStatus` with admin_id--{self.request.user.id}, for credit_id--{credit.id}.")
                    credit.status = Credit.Status.REJECTED
                    credit.save(update_fields=["status"])
                    return Response(CreditSerializer(credit).data, status=status.HTTP_200_OK)
                
                seller = Seller.objects.select_for_update().get(pk=credit.seller_id)

                Transaction.objects.create(
                    account=None,
                    seller=seller,
                    change=credit.amount,
                    type=Transaction.Type.INCREASE,
                    idempotency=idempotency,
                    balance_before=seller.total_balance,
                    balance_after=seller.total_balance + credit.amount,
                )

                seller.total_balance = F("total_balance") + credit.amount
                seller.save(update_fields=["total_balance"]) 

                credit.status = Credit.Status.APPROVED
                credit.save(update_fields=["status"])
                
                logger.info(f"approve status in `ChangeCreditStatus` with admin_id--{self.request.user.id}, for credit_id--{credit.id}.")
                return Response(CreditSerializer(credit).data, status=status.HTTP_200_OK)

            except (Credit.DoesNotExist, Seller.DoesNotExist, SellerAccount.DoesNotExist) as e:
                logger.warning(f"ERROR in `ChangeCreditStatus` a query didn't exist. \n {e}")
                return Response(ErrorResponses.OBJECT_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                logger.critical(f"ERROR in `ChangeCreditStatus` with admin_id--{self.request.user.id}, for credit_id--{credit.id}. \n {e}")
                raise