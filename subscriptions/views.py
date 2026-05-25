from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from adrf import generics, views
from django.conf import settings
from django.db import models
from django.utils import timezone
from drf_spectacular.utils import extend_schema
import math
import uuid
import requests

from .models import Subscription, PaymentHistory, PaymentMethod, Coupon
from organizations.models import Organization, OrganizationMembership
from .serializers import PlanSerializer, InitiateSubscriptionSerializer, VerifyPaymentSerializer
from .utils import verify_paystack_transaction, verify_flutterwave_transaction, verify_flutterwave_transaction_by_reference, get_plan_price



@extend_schema(tags=["Subscriptions"])
class PlanListView(generics.GenericAPIView):
    """
    Returns the list of available plans with their current prices.

    Prices are sourced from the PlanPricing DB table (admin-editable) and fall back
    to the hardcoded constants in constants.py when no DB record exists.

    Public — no authentication required so the marketing pricing page can call this.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PlanSerializer

    async def get(self, request):
        @sync_to_async
        def _sync_logic():
            import copy
            from .constants import PLAN_DETAILS
            from .models import PlanPricing

            plans = copy.deepcopy(PLAN_DETAILS)

            # Build a quick lookup of DB-stored prices, keyed by plan_type
            db_prices = {p.plan_type: p for p in PlanPricing.objects.filter(is_active=True)}

            for plan in plans:
                db = db_prices.get(plan['type'])
                if db:
                    plan['price_naira_monthly'] = float(db.price_ngn_monthly)
                    plan['price_naira_yearly']  = float(db.price_ngn_yearly)
                    plan['price_usd_monthly']   = float(db.price_usd_monthly)
                    plan['price_usd_yearly']    = float(db.price_usd_yearly)

            return Response({'plans': plans})
        return await _sync_logic()

@extend_schema(tags=["Subscriptions"])
class SubscriptionDetailView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    async def get(self, request, organization_id):
        @sync_to_async
        def _sync_logic():
            # 1. Verify Organization Membership & Permissions
            organization = None
        
            if str(organization_id) == str(request.user.id):
                organization = Organization.objects.filter(owner=request.user).first()
                if not organization:
                    # Auto-create a personal organization for this user if they don't have one
                    organization = Organization.objects.create(
                        name=f"{request.user.get_full_name() or request.user.username}'s Organization",
                        owner=request.user,
                        plan_type=getattr(request.user, 'plan_type', 'free')
                    )
                    OrganizationMembership.objects.create(user=request.user, organization=organization, role='owner')
            else:
                try:
                    membership = OrganizationMembership.objects.get(
                        user=request.user, 
                        organization_id=organization_id,
                        is_active=True
                    )
                    organization = membership.organization
                except OrganizationMembership.DoesNotExist:
                    return Response({'error': 'Organization not found or access denied'}, status=status.HTTP_403_FORBIDDEN)
                
            sub_data = None
            try:
                subscription = Subscription.objects.get(organization=organization)
                amount = 0
                if subscription.plan_type != 'free':
                    from .utils import get_plan_price
                    # Calculate current active subscription amount paid originally
                    amount = get_plan_price(subscription.plan_type, 'NGN', subscription.billing_cycle)

                sub_data = {
                    'id': str(subscription.id),
                    'plan_type': subscription.plan_type,
                    'status': subscription.status,
                    'start_date': subscription.start_date,
                    'end_date': subscription.end_date,
                    'next_billing_date': subscription.next_billing_date,
                    'billing_cycle': subscription.billing_cycle,
                    'amount': amount,
                    'currency': 'NGN',  # Assuming NGN as default
                    'payment_provider': subscription.payment_provider,
                    'cancel_at_period_end': subscription.cancel_at_period_end,
                    'next_plan_type': subscription.next_plan_type
                }
            except Subscription.DoesNotExist:
                pass
            
            payment_methods_qs = PaymentMethod.objects.filter(organization=organization)[:3]
            payment_methods = []
            for pm in payment_methods_qs:
                payment_methods.append({
                    'provider': pm.provider,
                    'card_type': pm.card_type or 'Card',
                    'last4': pm.card_last4,
                    'first6': pm.card_first6,
                    'expiry': pm.card_expiry,
                    'is_default': pm.is_default,
                    'status': 'working'
                })
            
            payments = PaymentHistory.objects.filter(organization=organization).order_by('-transaction_date')
            payments_data = []
            for p in payments:
                payments_data.append({
                    'id': str(p.id),
                    'amount': p.amount,
                    'currency': p.currency,
                    'status': p.status,
                    'plan_type': p.plan_type,
                    'transaction_date': p.transaction_date,
                    'reference': p.reference,
                    'payment_provider': p.payment_provider
                })
            
            return Response({
                'subscription': sub_data,
                'payment_methods': payment_methods,
                'invoices': payments_data
            })
        return await _sync_logic()

@extend_schema(tags=["Subscriptions"])
class InitiateSubscriptionView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InitiateSubscriptionSerializer

    async def post(self, request, organization_id):
        @sync_to_async
        def _sync_logic():
            # 1. Verify Organization Membership & Permissions
            organization = None
        
            # Case A: organization_id is the User's ID (Personal Account)
            if str(organization_id) == str(request.user.id):
                # Find or create a personal organization for this user
                # We look for an organization owned by the user that acts as their primary/personal org
                # For simplicity, we can use the first one they own, or create one if none exists.
                from workspaces.models import Workspace
            
                organization = Organization.objects.filter(owner=request.user).first()
                if not organization:
                    organization = Organization.objects.create(
                        name=f"{request.user.get_full_name() or request.user.username}'s Organization",
                        owner=request.user,
                        plan_type=request.user.plan_type or 'free'
                    )
                    OrganizationMembership.objects.create(user=request.user, organization=organization, role='owner')
            
                # Ensure orphaned workspaces are attached (Migration logic)
                Workspace.objects.filter(owner=request.user, organization__isnull=True).update(organization=organization)
            
            else:
                # Case B: organization_id is an actual Organization ID
                try:
                    membership = OrganizationMembership.objects.get(
                        user=request.user, 
                        organization_id=organization_id,
                        is_active=True
                    )
                    if membership.role not in ['owner', 'admin']:
                         return Response({'error': 'Only owners/admins can manage subscriptions'}, status=status.HTTP_403_FORBIDDEN)
                    organization = membership.organization
                
                except OrganizationMembership.DoesNotExist:
                    return Response({'error': 'Organization not found or access denied'}, status=status.HTTP_403_FORBIDDEN)
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
        
            plan_type = serializer.validated_data['plan_type']
            payment_provider = serializer.validated_data['payment_provider']
            currency = serializer.validated_data.get('currency', 'NGN')
            billing_cycle = serializer.validated_data.get('billing_cycle', 'monthly')
            callback_url = serializer.validated_data.get('callback_url', settings.FRONTEND_URL + '/billing/callback')
            coupon_code = serializer.validated_data.get('coupon_code', '').strip().upper()

            try:
                Subscription.objects.get(organization=organization)
            except Subscription.DoesNotExist:
                pass

            amount = get_plan_price(plan_type, currency, billing_cycle)

            if amount <= 0:
                 return Response({'error': 'Invalid plan or currency'}, status=status.HTTP_400_BAD_REQUEST)

            # Apply coupon discount if provided
            applied_coupon = None
            original_amount = amount
            if coupon_code:
                try:
                    coupon = Coupon.objects.get(code=coupon_code, is_active=True)
                    is_valid, msg = coupon.is_valid(plan_type)
                    if is_valid:
                        amount, _ = coupon.apply_discount(amount, currency)
                        applied_coupon = coupon
                    else:
                        return Response({'error': f'Coupon invalid: {msg}'}, status=status.HTTP_400_BAD_REQUEST)
                except Coupon.DoesNotExist:
                    return Response({'error': 'Invalid coupon code'}, status=status.HTTP_400_BAD_REQUEST)

        
            email = request.user.email
            reference = str(uuid.uuid4())

            authorization_url = ""
            access_code = ""

            try:
                if payment_provider == 'paystack':
                    url = "https://api.paystack.co/transaction/initialize"
                    headers = {
                        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                        "Content-Type": "application/json",
                    }
                    data = {
                        "email": email,
                        "amount": int(amount * 100), # Paystack expects kobo
                        "reference": reference,
                        "callback_url": callback_url,
                        "metadata": {
                            "organization_id": str(organization_id),
                            "plan_type": plan_type,
                            "billing_cycle": billing_cycle,
                            "custom_fields": [
                                {"display_name": "Organization", "variable_name": "organization_name", "value": organization.name},
                                {"display_name": "Plan", "variable_name": "plan_type", "value": plan_type},
                                {"display_name": "Billing Cycle", "variable_name": "billing_cycle", "value": billing_cycle.title()}
                            ]
                        }
                    }
                    response = requests.post(url, headers=headers, json=data, timeout=5)
                    res_data = response.json()
                
                    if not res_data['status']:
                        return Response({'error': 'Paystack initialization failed', 'details': res_data.get('message')}, status=status.HTTP_400_BAD_REQUEST)
                
                    authorization_url = res_data['data']['authorization_url']
                    access_code = res_data['data']['access_code']

                elif payment_provider == 'flutterwave':
                    url = "https://api.flutterwave.com/v3/payments"
                    headers = {
                        "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                        "Content-Type": "application/json",
                    }
                    data = {
                        "tx_ref": reference,
                        "amount": str(amount),
                        "currency": currency,
                        "redirect_url": callback_url,
                        "customer": {
                            "email": email,
                            "name": request.user.get_full_name() or email,
                        },
                        "meta": {
                            "organization_id": str(organization_id),
                            "plan_type": plan_type,
                            "billing_cycle": billing_cycle
                        },
                        "customizations": {
                            "title": f"BuildTracker {plan_type.title()} Plan ({billing_cycle.title()})",
                            "logo": "https://buildtracker.com/logo.png" # Replace with actual logo URL
                        }
                    }
                    response = requests.post(url, headers=headers, json=data, timeout=5)
                    res_data = response.json()

                    if res_data['status'] != 'success':
                         return Response({'error': 'Flutterwave initialization failed', 'details': res_data.get('message')}, status=status.HTTP_400_BAD_REQUEST)
                
                    authorization_url = res_data['data']['link']
                    access_code = reference # Map reference to access_code for Flutterwave
        
            except Exception as e:
                return Response({'error': f'Payment initialization error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            payment_metadata = {
                'initiated_by': request.user.email,
            }
            if applied_coupon:
                payment_metadata['coupon_code'] = applied_coupon.code
                payment_metadata['original_amount'] = str(original_amount)

            PaymentHistory.objects.create(
                organization=organization,
                amount=amount,
                currency=currency,
                payment_provider=payment_provider,
                reference=reference,
                status='pending',
                plan_type=plan_type,
                billing_cycle=billing_cycle,
                metadata=payment_metadata
            )

            return Response({
                'authorization_url': authorization_url,
                'access_code': access_code,
                'reference': reference
            })
        return await _sync_logic()

@extend_schema(
    tags=["Subscriptions"], 
    request={
        'multipart/form-data': VerifyPaymentSerializer,
        'application/json': VerifyPaymentSerializer
    }
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
async def verify_payment(request):
    @sync_to_async
    def _sync_logic():
        import logging
        logger = logging.getLogger('security')

        reference = request.data.get('reference')
        provider = request.data.get('provider') # paystack or flutterwave

        if not reference or not provider:
            return Response({'error': 'Reference and provider are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = PaymentHistory.objects.get(reference=reference)
        except PaymentHistory.DoesNotExist:
            # It's possible the payment history wasn't created if init failed, but user shouldn't force verify non-existent ref
            # Unless it's a webhook race condition. 
            # But for manual verify, we expect it.
            return Response({'error': 'Payment reference not found'}, status=status.HTTP_404_NOT_FOUND)

        if payment.status == 'success':
            return Response({'message': 'Payment already verified', 'status': 'success'})

        verification_data = None
        if provider == 'paystack':
            # For Paystack, we verify with the ref
            verification_data = verify_paystack_transaction(reference)
        elif provider == 'flutterwave':
            # For FW, we might need transaction ID, but let's assume valid ref verification support or use transaction_id if passed
            transaction_id = request.data.get('transaction_id') # FW often returns transaction_id on callback

            # Try verifying by ID if provided
            if transaction_id:
                 verification_data = verify_flutterwave_transaction(transaction_id)

            # If ID verification failed or ID wasn't provided, try verifying by reference
            if not verification_data:
                 verification_data = verify_flutterwave_transaction_by_reference(reference)

            if not verification_data:
                return Response({'error': 'Transaction verification failed. Please ensure the transaction was successful.'}, status=status.HTTP_400_BAD_REQUEST)

        if verification_data:
            from decimal import Decimal
            paid_amount = Decimal(0)

            if provider == 'paystack':
                amount_kobo = verification_data.get('amount', 0)
                paid_amount = Decimal(amount_kobo) / Decimal(100)
            elif provider == 'flutterwave':
                paid_amount = Decimal(str(verification_data.get('amount', 0)))

            if paid_amount < payment.amount:
                 msg = f"Potential Fraud Attempt: Amount mismatch. User: {request.user.email}, Ref: {reference}, Expected: {payment.amount}, Paid: {paid_amount}"
                 logger.warning(msg)
                 payment.status = 'failed'
                 payment.metadata['failure_reason'] = msg
                 payment.save()
                 return Response({'error': 'Payment verification failed: Amount paid does not match plan price.'}, status=status.HTTP_400_BAD_REQUEST)

            payment.status = 'success'
            payment.save()

            # Increment coupon used_count if one was applied to this payment
            coupon_code_used = payment.metadata.get('coupon_code')
            if coupon_code_used:
                Coupon.objects.filter(code=coupon_code_used).update(
                    used_count=models.F('used_count') + 1
                )

            organization = payment.organization

            auth_code = None
            sub_code = None
            email_token = None
            billing_email = None
            card_last4 = None
            card_type = None
            card_expiry = None
            card_first6 = None

            if provider == 'paystack':
                auth_data = verification_data.get('authorization', {})
                auth_code = auth_data.get('authorization_code')
                sub_code = verification_data.get('subscription_code')
                email_token = verification_data.get('email_token')
                billing_email = verification_data.get('customer', {}).get('email')
                card_last4 = auth_data.get('last4')
                card_type = auth_data.get('card_type', '').upper()
                card_first6 = auth_data.get('bin')
                exp_month = auth_data.get('exp_month')
                exp_year = auth_data.get('exp_year')
                if exp_month and exp_year:
                    card_expiry = f"{str(exp_month).zfill(2)}/{str(exp_year)[-2:]}"
            elif provider == 'flutterwave':
                # Flutterwave token structure varies, checking common paths
                auth_code = verification_data.get('card', {}).get('token')
                if not auth_code:
                     auth_code = verification_data.get('token')
                if not auth_code and 'data' in verification_data:
                     auth_code = verification_data.get('data', {}).get('card', {}).get('token')
                     if not auth_code:
                          auth_code = verification_data.get('data', {}).get('token')

                sub_id = verification_data.get('id')
                if not sub_id and 'data' in verification_data:
                     sub_id = verification_data.get('data', {}).get('id')
                sub_code = str(sub_id) if sub_id else verification_data.get('tx_ref')

                # Extract customer email
                billing_email = verification_data.get('customer', {}).get('email')
                if not billing_email and 'data' in verification_data:
                     billing_email = verification_data.get('data', {}).get('customer', {}).get('email')

                # Flutterwave card details
                fw_card = verification_data.get('card', {})
                if not fw_card and 'data' in verification_data:
                    fw_card = verification_data.get('data', {}).get('card', {})
                card_last4 = fw_card.get('last_4digits')
                card_type = (fw_card.get('type') or fw_card.get('issuer', '')).upper()
                card_first6 = fw_card.get('first_6digits')
                card_expiry = fw_card.get('expiry')

            new_plan = payment.plan_type
            existing_sub = Subscription.objects.filter(organization=organization).first()

            organization.plan_type = new_plan
            organization.save()
            if organization.owner:
                organization.owner.plan_type = new_plan
                organization.owner.save()

            days_to_add = 365 if payment.billing_cycle == 'yearly' else 30

            # Determine the base date to extend from
            if existing_sub and existing_sub.end_date and existing_sub.end_date > timezone.now() and existing_sub.status in ('active', 'past_due'):
                base_date = existing_sub.end_date
            else:
                base_date = timezone.now()

            new_end_date = base_date + timezone.timedelta(days=days_to_add)

            Subscription.objects.update_or_create(
                organization=organization,
                defaults={
                    'plan_type': new_plan,
                    'billing_cycle': payment.billing_cycle,
                    'status': 'active',
                    'payment_provider': provider,
                    'end_date': new_end_date,
                    'next_billing_date': new_end_date,
                    'grace_period_end': new_end_date + timezone.timedelta(days=3),
                    'authorization_code': auth_code,
                    'subscription_code': sub_code,
                    'email_token': email_token,
                    'billing_email': billing_email,
                    'cancel_at_period_end': False,
                    'next_plan_type': None,
                    'is_in_grace_period': False,
                    'retry_count': 0
                }
            )
            response_msg = f'Payment verified and your plan has been instantly updated to {new_plan.capitalize()}.'

            if card_last4 and provider:
                pm, _ = PaymentMethod.objects.update_or_create(
                    organization=organization,
                    provider=provider,
                    card_last4=card_last4,
                    defaults={
                        'card_type': card_type or '',
                        'card_expiry': card_expiry or '',
                        'card_first6': card_first6 or '',
                        'is_default': True,
                    }
                )
                PaymentMethod.objects.filter(organization=organization).exclude(id=pm.id).update(is_default=False)
                old_pms = PaymentMethod.objects.filter(organization=organization).order_by('-updated_at')[3:]
                PaymentMethod.objects.filter(id__in=[p.id for p in old_pms]).delete()

            return Response({'message': response_msg, 'status': 'success'})

        payment.status = 'failed'
        payment.save()
        return Response({'error': 'Payment verification failed'}, status=status.HTTP_400_BAD_REQUEST)

    return await _sync_logic()

@extend_schema(tags=["Subscriptions"])
class PaystackWebhookView(views.APIView):
    authentication_classes = []
    permission_classes = []

    async def post(self, request):
        @sync_to_async
        def _sync_logic():
            import logging
            logger = logging.getLogger('security')

            from .utils import verify_paystack_signature
            
            x_paystack_signature = request.headers.get('x-paystack-signature')
            if not verify_paystack_signature(request.body, x_paystack_signature):
                logger.warning(f"Invalid Paystack Signature from IP: {request.META.get('REMOTE_ADDR')}")
                return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
            
            event = request.data.get('event')
            data = request.data.get('data')

            from .tasks import process_paystack_webhook_task
            process_paystack_webhook_task.delay(event, data)

            return Response(status=status.HTTP_200_OK)
        return await _sync_logic()

@extend_schema(tags=["Subscriptions"])
class FlutterwaveWebhookView(views.APIView):
    authentication_classes = []
    permission_classes = []

    async def post(self, request):
        @sync_to_async
        def _sync_logic():
            import logging
            logger = logging.getLogger('security')

            from .utils import verify_flutterwave_signature
            
            signature = request.headers.get('verif-hash')
            if not verify_flutterwave_signature(signature):
                logger.warning(f"Invalid Flutterwave Signature from IP: {request.META.get('REMOTE_ADDR')}")
                return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)

            event = request.data.get('event')
            data = request.data.get('data')
            
            from .tasks import process_flutterwave_webhook_task
            process_flutterwave_webhook_task.delay(event, data)

            return Response(status=status.HTTP_200_OK)
        return await _sync_logic()

@extend_schema(tags=["Subscriptions"])
class CancelSubscriptionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    async def post(self, request, organization_id):
        @sync_to_async
        def _sync_logic():
            organization = None
            
            if str(organization_id) == str(request.user.id):
                organization = Organization.objects.filter(owner=request.user).first()
                if not organization:
                    return Response({'error': 'No personal organization found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                try:
                    membership = OrganizationMembership.objects.get(
                        user=request.user, 
                        organization_id=organization_id,
                        is_active=True
                    )
                    if membership.role not in ['owner', 'admin']:
                         return Response({'error': 'Only owners/admins can manage subscriptions'}, status=status.HTTP_403_FORBIDDEN)
                    organization = membership.organization
                except OrganizationMembership.DoesNotExist:
                     return Response({'error': 'Organization not found'}, status=status.HTTP_404_NOT_FOUND)

            try:
                subscription = organization.subscription
                subscription.cancel_at_period_end = True
                subscription.save()
                return Response({
                    'message': f'Subscription will be cancelled on {subscription.end_date}.',
                    'end_date': subscription.end_date
                })
            except Subscription.DoesNotExist:
                return Response({'error': 'No active subscription found'}, status=status.HTTP_404_NOT_FOUND)
        return await _sync_logic()

@extend_schema(tags=["Subscriptions"])
class DowngradeSubscriptionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    async def post(self, request, organization_id):
        @sync_to_async
        def _sync_logic():
            new_plan = request.data.get('plan_type')
            if not new_plan:
                 return Response({'error': 'plan_type is required'}, status=status.HTTP_400_BAD_REQUEST)

            organization = None
            
            if str(organization_id) == str(request.user.id):
                organization = Organization.objects.filter(owner=request.user).first()
                if not organization:
                    return Response({'error': 'No personal organization found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                try:
                    membership = OrganizationMembership.objects.get(
                        user=request.user, 
                        organization_id=organization_id,
                        is_active=True
                    )
                    if membership.role not in ['owner', 'admin']:
                         return Response({'error': 'Only owners/admins can manage subscriptions'}, status=status.HTTP_403_FORBIDDEN)
                    organization = membership.organization
                except OrganizationMembership.DoesNotExist:
                     return Response({'error': 'Organization not found'}, status=status.HTTP_404_NOT_FOUND)

            try:
                subscription = organization.subscription
                if subscription.plan_type == new_plan:
                    return Response({'error': 'You are already on this plan'}, status=status.HTTP_400_BAD_REQUEST)
                
                subscription.next_plan_type = new_plan
                subscription.cancel_at_period_end = False
                subscription.save()
                
                return Response({
                    'message': f'Subscription will switch to {new_plan} on {subscription.end_date}.',
                    'end_date': subscription.end_date,
                    'next_plan': new_plan
                })
            except Subscription.DoesNotExist:
                return Response({'error': 'No active subscription found'}, status=status.HTTP_404_NOT_FOUND)
        return await _sync_logic()


# ─── Coupon Validation ────────────────────────────────────────────────────────

@extend_schema(tags=["Subscriptions"])
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
async def validate_coupon(request):
    """
    Validate a coupon code and return the discounted price.

    Public endpoint — called from the checkout page before payment is initiated.

    Request body:
        code          — coupon code to validate (required)
        plan_type     — plan being purchased: starter | premium | custom (optional)
        currency      — NGN | USD (default: NGN)
        billing_cycle — monthly | yearly (default: monthly)

    Response (always 200):
        is_valid          — bool
        message           — human-readable result
        discount_type     — percentage | fixed_ngn | fixed_usd (only if valid)
        discount_value    — raw discount value (only if valid)
        original_amount   — base price for the plan/cycle in the given currency
        discounted_amount — price after discount applied
        savings           — amount saved
        currency          — currency used
    """
    @sync_to_async
    def _sync_logic():
        code = request.data.get('code', '').strip().upper()
        plan_type = request.data.get('plan_type', '').strip()
        currency = request.data.get('currency', 'NGN').upper()
        billing_cycle = request.data.get('billing_cycle', 'monthly').lower()

        if not code:
            return Response({'error': 'Coupon code is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            coupon = Coupon.objects.get(code=code)
        except Coupon.DoesNotExist:
            return Response({'is_valid': False, 'message': 'Invalid coupon code'})

        is_valid, message = coupon.is_valid(plan_type or None)

        original_amount = 0.0
        discounted_amount = 0.0
        savings = 0.0

        if plan_type:
            original_amount = get_plan_price(plan_type, currency, billing_cycle)
            if is_valid and original_amount > 0:
                discounted_amount, savings = coupon.apply_discount(original_amount, currency)
            else:
                discounted_amount = original_amount

        return Response({
            'is_valid':          is_valid,
            'message':           message,
            'discount_type':     coupon.discount_type if is_valid else None,
            'discount_value':    float(coupon.discount_value) if is_valid else None,
            'original_amount':   original_amount,
            'discounted_amount': discounted_amount,
            'savings':           savings,
            'currency':          currency,
        })
    return await _sync_logic()


# ─── Custom Pricing Calculator ────────────────────────────────────────────────

@extend_schema(tags=["Subscriptions"])
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
async def calculate_custom_price(request):
    """
    Calculate a bespoke (Custom/Enterprise) plan price from usage requirements.

    Based on §4 of the BuildTracker Pricing Guide v1.0.

    Formula:
        subtotal         = baseline + extra_workspace_cost + extra_member_cost + extra_storage_cost
        with_support     = subtotal × support_multiplier
        raw_price        = with_support × (1 + negotiation_buffer)
        floor_price      = CEIL(raw_price, 100)  — nearest ₦100 (or $1 for USD)
        quoted_price     = max(floor_price, minimum_quote)

    Request body:
        extra_workspaces — workspaces beyond the Premium limit of 5  (default 0)
        extra_members    — members beyond the Premium limit of 25     (default 0)
        extra_storage_gb — storage GB beyond the Premium limit of 20 GB (default 0)
        support_level    — standard | priority | dedicated            (default: standard)
        currency         — NGN | USD                                  (default: NGN)

    Response:
        line_items            — itemised breakdown [{label, amount}]
        subtotal              — sum before support multiplier
        support_level         — chosen support tier
        support_multiplier    — multiplier applied (1.00 / 1.15 / 1.25)
        subtotal_with_support — after support multiplier
        negotiation_buffer    — buffer fraction (0.25)
        raw_price             — price before rounding/minimum
        floor_price           — final quoted price
        minimum_quote         — minimum allowed quote for Custom plan
        is_minimum_applied    — True if floor_price was clamped up to minimum_quote
        currency              — currency used
    """
    @sync_to_async
    def _sync_logic():
        from .constants import CUSTOM_PRICING

        try:
            extra_workspaces = max(0, int(request.data.get('extra_workspaces', 0)))
            extra_members    = max(0, int(request.data.get('extra_members', 0)))
            extra_storage_gb = max(0.0, float(request.data.get('extra_storage_gb', 0)))
        except (ValueError, TypeError):
            return Response(
                {'error': 'extra_workspaces, extra_members, and extra_storage_gb must be numbers'},
                status=status.HTTP_400_BAD_REQUEST
            )

        support_level = request.data.get('support_level', 'standard')
        currency      = request.data.get('currency', 'NGN').upper()

        if support_level not in CUSTOM_PRICING['support_multiplier']:
            choices = list(CUSTOM_PRICING['support_multiplier'].keys())
            return Response({'error': f'support_level must be one of: {choices}'}, status=status.HTTP_400_BAD_REQUEST)

        if currency not in ('NGN', 'USD'):
            return Response({'error': 'currency must be NGN or USD'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Baseline — starts at Premium plan price
        baseline = CUSTOM_PRICING['baseline'][currency]

        # 2. Per-unit add-ons
        workspace_cost = extra_workspaces * CUSTOM_PRICING['extra_workspace'][currency]
        member_cost    = extra_members    * CUSTOM_PRICING['extra_member'][currency]
        # Storage billed in 10 GB blocks, ceil to nearest block
        storage_blocks = math.ceil(extra_storage_gb / 10) if extra_storage_gb > 0 else 0
        storage_cost   = storage_blocks * CUSTOM_PRICING['extra_storage_per_10gb'][currency]

        subtotal = baseline + workspace_cost + member_cost + storage_cost

        # 3. Support tier multiplier
        support_mult          = CUSTOM_PRICING['support_multiplier'][support_level]
        subtotal_with_support = subtotal * support_mult

        # 4. Negotiation buffer (+25%)
        buffer    = CUSTOM_PRICING['negotiation_buffer']
        raw_price = subtotal_with_support * (1 + buffer)

        # 5. Round up: nearest ₦100 for NGN, nearest $1 for USD
        if currency == 'NGN':
            floor_price = math.ceil(raw_price / 100) * 100
        else:
            floor_price = math.ceil(raw_price)

        # 6. Enforce minimum quote — never quote below 3× Premium
        minimum_quote      = CUSTOM_PRICING['minimum_quote_ngn'] if currency == 'NGN' else CUSTOM_PRICING['minimum_quote_usd']
        is_minimum_applied = floor_price < minimum_quote
        floor_price        = max(floor_price, minimum_quote)

        # Build itemised line items (only show add-ons that are > 0)
        line_items = [
            {'label': 'Premium baseline (Custom plan starts here)', 'amount': baseline},
        ]
        if extra_workspaces > 0:
            line_items.append({
                'label':  f'{extra_workspaces} extra workspace(s) × {CUSTOM_PRICING["extra_workspace"][currency]} {currency}',
                'amount': workspace_cost,
            })
        if extra_members > 0:
            line_items.append({
                'label':  f'{extra_members} extra member(s) × {CUSTOM_PRICING["extra_member"][currency]} {currency}',
                'amount': member_cost,
            })
        if extra_storage_gb > 0:
            line_items.append({
                'label':  f'{storage_blocks} × 10 GB storage block(s) ({extra_storage_gb:.0f} GB total)',
                'amount': storage_cost,
            })

        return Response({
            'line_items':             line_items,
            'subtotal':               subtotal,
            'support_level':          support_level,
            'support_multiplier':     support_mult,
            'subtotal_with_support':  subtotal_with_support,
            'negotiation_buffer':     buffer,
            'raw_price':              round(raw_price, 2),
            'floor_price':            floor_price,
            'minimum_quote':          minimum_quote,
            'is_minimum_applied':     is_minimum_applied,
            'currency':               currency,
        })
    return await _sync_logic()
