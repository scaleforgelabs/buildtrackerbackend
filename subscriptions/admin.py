from django.contrib import admin
from .models import Subscription, PaymentHistory

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('organization', 'plan_type', 'billing_cycle', 'status', 'start_date', 'next_billing_date')
    list_filter = ('plan_type', 'status')
    search_fields = ('organization__name', 'subscription_code', 'email_token')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(PaymentHistory)
class PaymentHistoryAdmin(admin.ModelAdmin):
    list_display = ('organization', 'amount', 'currency', 'status', 'plan_type', 'billing_cycle', 'transaction_date')
    list_filter = ('status', 'plan_type', 'payment_provider')
    search_fields = ('organization__name', 'reference')
    readonly_fields = ('transaction_date',)
