from django.contrib import admin
from .models import Subscription, PaymentHistory, Coupon, PlanPricing

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

@admin.register(PlanPricing)
class PlanPricingAdmin(admin.ModelAdmin):
    list_display  = ('plan_type', 'price_ngn_monthly', 'price_ngn_yearly', 'price_usd_monthly', 'price_usd_yearly', 'is_active', 'updated_at', 'updated_by')
    list_filter   = ('is_active',)
    readonly_fields = ('updated_at', 'updated_by')

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'discount_value', 'used_count', 'max_uses', 'is_active', 'valid_from', 'valid_until', 'created_at')
    list_filter = ('discount_type', 'is_active')
    search_fields = ('code', 'description')
    readonly_fields = ('used_count', 'created_at', 'updated_at')
    fieldsets = (
        ('Coupon Code', {'fields': ('code', 'description', 'is_active')}),
        ('Discount',    {'fields': ('discount_type', 'discount_value')}),
        ('Usage Limits',{'fields': ('max_uses', 'used_count')}),
        ('Validity',    {'fields': ('valid_from', 'valid_until')}),
        ('Eligibility', {'fields': ('applicable_plans',),
                         'description': "Leave empty to apply to all plans. Enter a JSON list e.g. [\"starter\", \"premium\"]."}),
        ('Timestamps',  {'fields': ('created_at', 'updated_at')}),
    )
