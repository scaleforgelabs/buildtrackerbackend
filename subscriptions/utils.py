import requests
from django.conf import settings
import hmac
import hashlib

def verify_paystack_signature(payload, signature):
    """
    Verify Paystack webhook signature.
    
    Args:
        payload: Raw request body (bytes)
        signature: x-paystack-signature header value
    
    Returns:
        Boolean indicating if signature is valid
    """
    if not signature:
        return False
    
    computed_signature = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
        payload,
        hashlib.sha512
    ).hexdigest()
    
    return hmac.compare_digest(computed_signature, signature)

def verify_flutterwave_signature(signature):
    """
    Verify Flutterwave webhook signature.
    
    Args:
        signature: verif-hash header value
    
    Returns:
        Boolean indicating if signature is valid
    """
    if not signature:
        return False
    
    secret_hash = settings.FLUTTERWAVE_SECRET_HASH
    return hmac.compare_digest(signature, secret_hash)


def verify_paystack_transaction(reference):
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] is True and data['data']['status'] == 'success':
                return data['data']
    except requests.RequestException:
        pass
    return None

def charge_paystack_authorization(amount, email, authorization_code):
    url = "https://api.paystack.co/transaction/charge_authorization"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    data = { 
        "amount": int(amount * 100), # Paystack expects kobo
        "email": email, 
        "authorization_code": authorization_code
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            res_data = response.json()
            if res_data['status'] is True and res_data['data']['status'] == 'success':
                 return True, res_data['data']
            return False, res_data
        return False, response.json()
    except requests.RequestException as e:
        return False, str(e)

def verify_flutterwave_transaction(transaction_id):
    url = f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify"
    headers = {
        "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success' and data['data']['status'] == 'successful':
                return data['data']
    except requests.RequestException:
        pass
    return None

def verify_flutterwave_transaction_by_reference(tx_ref):
    url = f"https://api.flutterwave.com/v3/transactions/verify_by_reference?tx_ref={tx_ref}"
    headers = {
        "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success' and data['data']['status'] == 'successful':
                return data['data']
    except requests.RequestException:
        pass
    return None



def get_plan_price(plan_type, currency='NGN', billing_cycle='monthly'):
    """
    Return the amount to charge for a given plan, currency, and billing cycle.

    Priority: DB record (PlanPricing) → hardcoded fallback constants.
    This means admins can update prices via the admin dashboard without a code deploy.

    Legacy plan keys (pro → starter, business → premium, enterprise → custom) are
    normalised before the lookup so existing subscriptions keep working.

    Returns:
        float — amount in main currency units (NGN or USD), never kobo/cents.
                Returns 0.0 for unknown / free plans.
    """
    # Normalise legacy aliases to canonical plan names
    ALIAS = {
        'pro':        'starter',
        'business':   'premium',
        'enterprise': 'custom',
    }
    canonical = ALIAS.get(plan_type, plan_type)

    # 1. Try the database (admin-configurable prices)
    try:
        from .models import PlanPricing
        pricing = PlanPricing.objects.get(plan_type=canonical, is_active=True)
        if billing_cycle == 'yearly':
            rate = pricing.price_ngn_yearly if currency == 'NGN' else pricing.price_usd_yearly
            return float(rate) * 12   # Charge the full year upfront
        else:
            rate = pricing.price_ngn_monthly if currency == 'NGN' else pricing.price_usd_monthly
            return float(rate)
    except Exception:
        pass  # Fall through to hardcoded constants

    # 2. Hardcoded fallback (used before migrations run or if DB record is missing)
    MONTHLY = {
        'starter':  {'NGN': 9900,  'USD': 6},
        'premium':  {'NGN': 24900, 'USD': 15},
        'custom':   {'NGN': 95000, 'USD': 60},
    }
    YEARLY_MONTHLY = {
        'starter':  {'NGN': 7900,  'USD': 5},
        'premium':  {'NGN': 19900, 'USD': 12},
        'custom':   {'NGN': 75000, 'USD': 45},
    }

    if canonical not in MONTHLY:
        return 0.0

    if billing_cycle == 'yearly':
        monthly_rate = YEARLY_MONTHLY[canonical].get(currency, 0)
        return float(monthly_rate * 12)

    return float(MONTHLY[canonical].get(currency, 0))

def calculate_prorated_amount(current_plan, new_plan, days_remaining, currency='NGN', billing_cycle='monthly'):
    """
    Calculate prorated amount for upgrading mid-cycle.
    
    Args:
        current_plan: Current subscription plan type
        new_plan: New plan type to upgrade to
        days_remaining: Days remaining in current billing cycle
        currency: Currency code (NGN or USD)
        billing_cycle: The chosen billing cycle ('monthly' or 'yearly')
    
    Returns:
        Prorated amount to charge for the upgrade
    """
    if current_plan == 'free':
        # Upgrading from free, charge full price for remaining days
        new_plan_price = get_plan_price(new_plan, currency, billing_cycle)
        total_days = 365 if billing_cycle == 'yearly' else 30
        return (new_plan_price * days_remaining) / total_days
    
    # Calculate price difference
    current_plan_price = get_plan_price(current_plan, currency, billing_cycle)
    new_plan_price = get_plan_price(new_plan, currency, billing_cycle)
    price_difference = new_plan_price - current_plan_price
    
    # If downgrading (negative difference), return 0 (no charge)
    if price_difference <= 0:
        return 0
    
    # Calculate prorated amount for remaining days
    prorated_amount = (price_difference * days_remaining) / 30
    
    return max(prorated_amount, 0)  # Ensure non-negative

def charge_flutterwave_token(amount, email, token, currency='NGN', tx_ref=None):
    url = "https://api.flutterwave.com/v3/tokenized-charges"
    headers = {
        "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    import uuid
    if not tx_ref:
        tx_ref = str(uuid.uuid4())
        
    data = {
        "token": token,
        "currency": currency,
        "country": "NG",
        "amount": amount,
        "email": email,
        "tx_ref": tx_ref,
        "redirect_url": "https://google.com"
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        res_data = response.json()
        if response.status_code == 200 and res_data['status'] == 'success':
             return True, res_data['data']
        return False, res_data
    except requests.RequestException as e:
        return False, str(e)
