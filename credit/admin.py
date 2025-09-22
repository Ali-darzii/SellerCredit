from django.contrib import admin

from credit import models

admin.site.register(models.Credit)
admin.site.register(models.Transaction)