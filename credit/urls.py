from django.urls import path

from credit.api.v1 import credit
from credit.api.v1 import seller_acount

urlpatterns = [
    path("", credit.CreateCreditView.as_view(), name="create_credit"),
    path("change/status/<int:credit_id>", credit.ChangeCreditStatusView.as_view(), name="change_credit_status"),
    
    
    path("account/charge", seller_acount.ChargePhoneView.as_view(), name="charge_phone"),
    
]