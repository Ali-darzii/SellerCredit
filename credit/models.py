from django.db import models
from django.core.validators import MinValueValidator

from user.models import SellerAccount, Seller
class Credit(models.Model):

    class Status(models.TextChoices):
        PENDING = ("pending", "Pending")
        APPROVED = ("approved", "Approved")
        REJECTED = ("rejected", "Rejected")
        
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name="credit_requests")
    amount = models.BigIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    
    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gte=1), name='amount_gte_1')
        ]
        

    def __str__(self):
        return f"{self.seller.username} | {self.amount}"
    
    
class Transaction(models.Model):
    class Type(models.TextChoices):
        INCREASE = ("Increase", "Increase Balance")
        SALE = ("Sale", "Charge Sale")
    
    account = models.ForeignKey(SellerAccount, on_delete=models.CASCADE, related_name="transactions", null=True)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name="transactions", null=True)
    change = models.BigIntegerField(validators=[MinValueValidator(1)])
    type = models.CharField(max_length=10, choices=Type.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    idempotency = models.CharField(max_length=150, unique=True)
    balance_before = models.BigIntegerField()
    balance_after = models.BigIntegerField()
    
    
    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(change__gte=1), name='change_gte_1')
        ]
        
        
    def __str__(self):
        if self.seller:
            return f"{self.seller.username} | {self.change}"
        return f"{self.account.seller.username} | {self.change}"