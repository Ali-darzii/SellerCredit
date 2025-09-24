from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator

from utils.utils import retry_on_conflict

class Seller(AbstractUser):
    total_balance = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    
    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(total_balance__gte=0), name='total_balance_non_negative')
        ]
            
    def __str__(self):
        return self.username

    @retry_on_conflict(max_retries=3)
    def safe_transaction_save(self):
        """ avoiding dead lock """
        self.save(update_fields=["total_balance"])
    
    
class SellerAccount(models.Model):
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name="accounts")
    balance = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    phone_number = models.CharField(max_length=11, unique=True)
    
    
    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(balance__gte=0), name='balance_non_negative')
        ]
        
    def __str__(self):
        return f"{self.seller.username} | {self.phone_number}"
    
    @retry_on_conflict(max_retries=3)
    def safe_transaction_save(self):
        """ avoiding dead lock """
        self.save(update_fields=["balance"])