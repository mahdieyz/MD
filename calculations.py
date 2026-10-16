import re

def apply_percentage(base_price: float, percentage: float) -> float:
    """
    اعمال درصد روی قیمت پایه (مثبت برای درصد افزایشی، منفی برای تخفیف)
    مثال: apply_percentage(1000000, 20) -> 1200000.0
    """
    return base_price * (1 + (percentage / 100.0))

def calculate_final_price(base_price: float, markup_percent: float = 0, discount_percent: float = 0) -> dict:
    """
    محاسبه کامل قیمت با احتساب درصد اضافه (مانند لیست بعلاوه ۲۰٪) و درصد تخفیف
    """
    price_after_markup = base_price * (1 + (markup_percent / 100.0))
    discount_amount = price_after_markup * (discount_percent / 100.0)
    final_price = price_after_markup - discount_amount

    return {
        "base_price": base_price,
        "markup_percent": markup_percent,
        "discount_percent": discount_percent,
        "price_after_markup": price_after_markup,
        "discount_amount": discount_amount,
        "final_price": final_price
    }

def format_price(amount: float, unit: str = "تومان", persian_digits: bool = True) -> str:
    """
    فرمت‌دهی عددی قیمت با جداکننده سه رقمی و واحد پول
    مثال: 1200000 -> ۱,۲۰۰,۰۰۰ تومان
    """
    formatted = f"{int(round(amount)):,}"
    if persian_digits:
        formatted = to_persian_digits(formatted)
    return f"{formatted} {unit}".strip()

def to_persian_digits(text_or_number) -> str:
    """
    تبدیل اعداد انگلیسی به اعداد فارسی
    مثال: 123456 -> ۱۲۳۴۵۶
    """
    str_val = str(text_or_number)
    fa_digits = "۰۱۲۳۴۵۶۷۸۹"
    en_digits = "0123456789"
    translation_table = str.maketrans(en_digits, fa_digits)
    return str_val.translate(translation_table)

def to_english_digits(text_or_number) -> str:
    """
    تبدیل اعداد فارسی به انگلیسی
    """
    str_val = str(text_or_number)
    fa_digits = "۰۱۲۳۴۵۶۷۸۹"
    en_digits = "0123456789"
    translation_table = str.maketrans(fa_digits, en_digits)
    return str_val.translate(translation_table)

def extract_price_from_text(text: str) -> float:
    """
    استخراج اولین عدد قیمت از یک متن (پشتیبانی از اعداد فارسی و انگلیسی)
    """
    if not text:
        return 0.0
    
    clean_text = to_english_digits(text).replace(",", "").replace("،", "")
    numbers = re.findall(r'\d+', clean_text)
    if numbers:
        return float(numbers[0])
    return 0.0

def generate_price_caption(base_price: float, markup_percent: float = 20, note: str = "") -> str:
    """
    تولید متن توضیحات قیمت برای زیر کاتالوگ یا تصویر
    """
    calc = calculate_final_price(base_price, markup_percent=markup_percent)
    
    caption = f"💵 **قیمت پایه لیست:** {format_price(calc['base_price'])}\n"
    if markup_percent != 0:
        sign = "+" if markup_percent > 0 else ""
        caption += f"📊 **درصد تغییرات:** {to_persian_digits(sign + str(markup_percent))}٪\n"
        caption += f"✅ **قیمت نهایی:** {format_price(calc['final_price'])}\n"
    
    if note:
        caption += f"\n📝 **توضیحات:** {note}"
        
    return caption
