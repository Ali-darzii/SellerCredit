from rest_framework import serializers
from credit.models import Credit
from user.models import SellerAccount

class CreditSerializer(serializers.ModelSerializer):
    class Meta:
        model = Credit
        fields  = "__all__"


class CreateCreditSerializer(serializers.ModelSerializer):
    amount = serializers.IntegerField(min_value=1)

    class Meta:
        model = Credit
        exclude = ("status", "created_at", "updated_at", "seller")
    
    
class ChangeCreditStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Credit.Status.choices)
    
    
class ChargePhoneSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=11, min_length=11)
    amount = serializers.IntegerField(min_value=1)