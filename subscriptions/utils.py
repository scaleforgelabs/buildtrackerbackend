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
    # Prices in base units (kobo for NGN, cents for USD)? No, usually API expects main unit or we handle conversion.
    # Let's return amount in main unit (e.g. 6000 NGN)
    
    PRICES = {
        'pro': {'NGN': 6000, 'USD': 6},
        'business': {'NGN': 18000, 'USD': 18},
        'enterprise': {'NGN': 100000, 'USD': 100}, # Placeholder
    }
    
    base_price = 0
    if plan_type in PRICES:
        base_price = PRICES[plan_type].get(currency, 0)
        
    if billing_cycle == 'yearly':
        # 12 months * 85% (15% discount)
        return float(base_price * 12 * 0.85)
        
    return float(base_price)

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
