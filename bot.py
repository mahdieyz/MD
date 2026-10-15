import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)
from database import Database
from calculations import Calc, fmt, fmtp

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

db = Database()
TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",")]

# States
L, W, H, T, AREA, COL_W, COL_D, COL_H, COL_RC, COL_RD = range(10)
EA, EF, ES, EQ = range(10, 14)
CV = 14

def main_kb():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🧮 محاسبه‌گر"), KeyboardButton("💰 برآورد هزینه")],
        [KeyboardButton("📦 قیمت مصالح"), KeyboardButton("📐 تبدیل واحد")],
        [KeyboardButton("📋 تاریخچه"), KeyboardButton("ℹ️ راهنما")],
    ], resize_keyboard=True)

def cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel")]])

def back_kb(cd="back_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=cd)]])

# ── START ──
async def start(update: Update, ctx):
    u = update.effective_user
    db.add_user(u.id, u.username, u.first_name, u.last_name)
    await update.message.reply_text(
        f"🏗 *ربات محاسبات ساختمانی*\n\nسلام {u.first_name} عزیز! 👋\n\n"
        "🔹 محاسبه مصالح ساختمانی\n🔹 برآورد هزینه ساخت\n"
        "🔹 قیمت روز مصالح\n🔹 تبدیل واحدها\n\n"
        "از منوی زیر انتخاب کنید: 👇",
        parse_mode="Markdown", reply_markup=main_kb())

async def help_cmd(update: Update, ctx):
    await update.message.reply_text(
        "📖 *راهنما*\n\n"
        "🧮 محاسبه‌گر: آجر، بتن، میلگرد، رنگ، کاشی، گچ، عایق، فونداسیون، ستون\n"
        "💰 برآورد: تخمین هزینه ساخت ساختمان\n"
        "📦 مصالح: قیمت روز مصالح\n"
        "📐 تبدیل: متر، فوت، کیلوگرم و...\n\n"
        "⚠️ قیمت‌ها تقریبی هستند.",
        parse_mode="Markdown")

# ── MENU ──
async def menu(update: Update, ctx):
    t = update.message.text
    db.update_activity(update.effective_user.id)
    if "محاسبه" in t:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧱 آجر", callback_data="c_brick"), InlineKeyboardButton("🏗 بتن", callback_data="c_concrete")],
            [InlineKeyboardButton("📏 میلگرد", callback_data="c_rebar"), InlineKeyboardButton("🎨 رنگ", callback_data="c_paint")],
            [InlineKeyboardButton("🏠 سیمان", callback_data="c_cement"), InlineKeyboardButton("📐 کاشی", callback_data="c_tile")],
            [InlineKeyboardButton("🔧 گچ", callback_data="c_gypsum"), InlineKeyboardButton("💧 عایق", callback_data="c_water")],
            [InlineKeyboardButton("📊 فونداسیون", callback_data="c_found"), InlineKeyboardButton("🏢 ستون", callback_data="c_col")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]])
        await update.message.reply_text("🧮 نوع محاسبه را انتخاب کنید:", reply_markup=kb)
    elif "برآورد" in t:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 مسکونی", callback_data="e_res")],
            [InlineKeyboardButton("🏢 تجاری", callback_data="e_com")],
            [InlineKeyboardButton("🏭 صنعتی", callback_data="e_ind")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]])
        await update.message.reply_text("💰 نوع ساختمان:", reply_markup=kb)
    elif "مصالح" in t:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧱 پایه", callback_data="m_مصالح پایه"), InlineKeyboardButton("🔩 فلزات", callback_data="m_فلزات")],
            [InlineKeyboardButton("🏗 بتن", callback_data="m_بتن"), InlineKeyboardButton("🎨 نازک‌کاری", callback_data="m_نازک‌کاری")],
            [InlineKeyboardButton("💧 عایق", callback_data="m_عایق"), InlineKeyboardButton("🚪 در/پنجره", callback_data="m_در و پنجره")],
            [InlineKeyboardButton("🔧 تاسیسات", callback_data="m_تاسیسات"), InlineKeyboardButton("📋 همه", callback_data="m_all")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]])
        await update.message.reply_text("📦 دسته‌بندی:", reply_markup=kb)
    elif "تبدیل" in t:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📏 متر↔فوت", callback_data="v_mf"), InlineKeyboardButton("📐 m²↔ft²", callback_data="v_m2")],
            [InlineKeyboardButton("📦 m³↔لیتر", callback_data="v_m3"), InlineKeyboardButton("⚖️ kg↔lb", callback_data="v_kg")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]])
        await update.message.reply_text("📐 نوع تبدیل:", reply_markup=kb)
    elif "تاریخچه" in t:
        calcs = db.get_user_calculations(update.effective_user.id)
        if not calcs:
            await update.message.reply_text("📋 تاریخچه خالی است.")
            return
        names = {"brick":"🧱 آجر","concrete":"🏗 بتن","rebar":"📏 میلگرد","paint":"🎨 رنگ",
                 "cement":"🏠 سیمان","tile":"📐 کاشی","gypsum":"🔧 گچ","water":"💧 عایق",
                 "found":"📊 فونداسیون","col":"🏢 ستون","est":"💰 برآورد"}
        txt = "📋 *۱۰ محاسبه آخر:*\n\n"
        for i, c in enumerate(calcs, 1):
            txt += f"{i}. {names.get(c['calc_type'], c['calc_type'])} - {c['created_at'][:16]}\n"
        await update.message.reply_text(txt, parse_mode="Markdown")
    elif "راهنما" in t:
        await help_cmd(update, ctx)

# ── CALCULATOR ──
async def calc_entry(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    if q.data == "back_main":
        await q.edit_message_text("از منو انتخاب کنید 👇"); return ConversationHandler.END
    prompts = {
        "c_brick": ("brick", "طول اتاق (متر):", L),
        "c_concrete": ("concrete", "طول سطح بتن‌ریزی (متر):", L),
        "c_rebar": ("rebar", "مساحت سقف (متر مربع):", AREA),
        "c_paint": ("paint", "مساحت رنگ‌آمیزی (متر مربع):", AREA),
        "c_cement": ("cement", "مساحت سیمانکاری (متر مربع):", AREA),
        "c_tile": ("tile", "طول سطح کاشی (متر):", L),
        "c_gypsum": ("gypsum", "مساحت گچ‌کاری (متر مربع):", AREA),
        "c_water": ("water", "مساحت عایق‌کاری (متر مربع):", AREA),
        "c_found": ("found", "طول فونداسیون (متر):", L),
        "c_col": ("col", "عرض ستون (سانتیمتر):", COL_W),
    }
    if q.data in prompts:
        ct, prompt, state = prompts[q.data]
        ctx.user_data["ct"] = ct
        ctx.user_data["d"] = {}
        await q.edit_message_text(f"🧮 {prompt}", reply_markup=cancel_kb())
        return state
    return ConversationHandler.END

async def get_l(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",","."))
        if v <= 0: raise ValueError
        ctx.user_data["d"]["l"] = v
        ct = ctx.user_data["ct"]
        if ct in ("brick","concrete","found","tile"):
            await update.message.reply_text("عرض (متر):", reply_markup=cancel_kb()); return W
    except: await update.message.reply_text("⚠️ عدد مثبت وارد کنید:"); return L

async def get_w(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",","."))
        if v <= 0: raise ValueError
        ctx.user_data["d"]["w"] = v
        ct = ctx.user_data["ct"]
        if ct == "brick":
            await update.message.reply_text("ارتفاع دیوار (متر):", reply_markup=cancel_kb()); return H
        elif ct in ("concrete","found"):
            await update.message.reply_text("ضخامت/عمق (متر):", reply_markup=cancel_kb()); return T
        elif ct == "tile":
            return await show_tile(update, ctx)
    except: await update.message.reply_text("⚠️ عدد مثبت:"); return W

async def get_h(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",","."))
        if v <= 0: raise ValueError
        ctx.user_data["d"]["h"] = v
        if ctx.user_data["ct"] == "brick": return await show_brick(update, ctx)
    except: await update.message.reply_text("⚠️ عدد مثبت:"); return H

async def get_t(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",","."))
        if v <= 0: raise ValueError
        ctx.user_data["d"]["t"] = v
        ct = ctx.user_data["ct"]
        if ct == "concrete": return await show_concrete(update, ctx)
        elif ct == "found": return await show_found(update, ctx)
    except: await update.message.reply_text("⚠️ عدد مثبت:"); return T

async def get_area(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",","."))
        if v <= 0: raise ValueError
        ctx.user_data["d"]["a"] = v
        ct = ctx.user_data["ct"]
        if ct == "rebar": return await show_rebar(update, ctx)
        elif ct == "paint": return await show_paint(update, ctx)
        elif ct == "cement": return await show_cement(update, ctx)
        elif ct == "gypsum": return await show_gypsum(update, ctx)
        elif ct == "water": return await show_water(update, ctx)
    except: await update.message.reply_text("⚠️ عدد مثبت:"); return AREA

# Column
async def get_cw(update: Update, ctx):
    try:
        v = float(update.message.text); ctx.user_data["d"]["cw"] = v/100
        await update.message.reply_text("عمق ستون (سانتیمتر):", reply_markup=cancel_kb()); return COL_D
    except: await update.message.reply_text("⚠️ عدد:"); return COL_W

async def get_cd(update: Update, ctx):
    try:
        v = float(update.message.text); ctx.user_data["d"]["cd"] = v/100
        await update.message.reply_text("ارتفاع ستون (متر):", reply_markup=cancel_kb()); return COL_H
    except: await update.message.reply_text("⚠️ عدد:"); return COL_D

async def get_ch(update: Update, ctx):
    try:
        v = float(update.message.text); ctx.user_data["d"]["ch"] = v
        await update.message.reply_text("تعداد میلگرد اصلی (مثلا 8):", reply_markup=cancel_kb()); return COL_RC
    except: await update.message.reply_text("⚠️ عدد:"); return COL_H

async def get_crc(update: Update, ctx):
    try:
        v = int(update.message.text); ctx.user_data["d"]["crc"] = v
        await update.message.reply_text("قطر میلگرد (میلیمتر، مثلا 16):", reply_markup=cancel_kb()); return COL_RD
    except: await update.message.reply_text("⚠️ عدد صحیح:"); return COL_RC

async def get_crd(update: Update, ctx):
    try:
        v = int(update.message.text); ctx.user_data["d"]["crd"] = v
        return await show_col(update, ctx)
    except: await update.message.reply_text("⚠️ عدد:"); return COL_RD

# ── SHOW RESULTS ──
async def show_brick(update, ctx):
    d = ctx.user_data["d"]
    r = Calc.brick(d["l"], d["w"], d["h"])
    bp = db.get_material("brick"); cp = db.get_material("cement")
    cost = r["waste"]*(bp["price"] if bp else 1200) + r["cement_bags"]*(cp["price"] if cp else 85000)
    txt = (f"🧱 *نتیجه آجرچینی*\n\n"
           f"📏 {d['l']}×{d['w']}×{d['h']} متر\n\n"
           f"├ مساحت دیوار: {r['wall_area']} m²\n"
           f"├ آجر مورد نیاز: {fmt(r['waste'])} عدد\n"
           f"├ سیمان: {r['cement_bags']} کیسه\n"
           f"├ ماسه: {r['sand_tons']} تن\n\n"
           f"💰 *هزینه تقریبی: {fmtp(cost)}*")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(update.effective_user.id, "brick", d, r)
    return ConversationHandler.END

async def show_concrete(update, ctx):
    d = ctx.user_data["d"]; r = Calc.concrete(d["l"], d["w"], d["t"])
    cp = db.get_material("concrete")
    cost = r["volume_waste"]*(cp["price"] if cp else 1800000)
    txt = (f"🏗 *نتیجه بتن*\n\n"
           f"├ حجم: {r['volume']} m³ (با پرت: {r['volume_waste']})\n"
           f"├ سیمان: {r['cement_bags']} کیسه\n"
           f"├ ماسه: {fmt(r['sand_kg'])} kg\n"
           f"├ شن: {fmt(r['gravel_kg'])} kg\n"
           f"├ آب: {r['water_l']} لیتر\n\n"
           f"💰 *هزینه: {fmtp(cost)}*")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(update.effective_user.id, "concrete", d, r)
    return ConversationHandler.END

async def show_rebar(update, ctx):
    d = ctx.user_data["d"]; r = Calc.rebar(d["a"])
    rp = db.get_material("rebar")
    cost = r["rebar_waste"]*(rp["price"] if rp else 32000)
    txt = (f"📏 *نتیجه میلگرد*\n\n"
           f"├ مساحت: {d['a']} m²\n"
           f"├ میلگرد: {fmt(r['rebar_waste'])} kg\n\n"
           f"💰 *هزینه: {fmtp(cost)}*")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(update.effective_user.id, "rebar", d, r)
    return ConversationHandler.END

async def show_paint(update, ctx):
    d = ctx.user_data["d"]; r = Calc.paint(d["a"])
    pp = db.get_material("paint")
    cost = d["a"]*(pp["price"] if pp else 45000)
    txt = (f"🎨 *نتیجه رنگ*\n\n"
           f"├ مساحت: {d['a']} m²\n"
           f"├ رنگ: {r['waste_liters']} لیتر\n"
           f"├ قوطی ۴ لیتری: {r['gallon_4l']} عدد\n\n"
           f"💰 *هزینه: {fmtp(cost)}*")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(update.effective_user.id, "paint", d, r)
    return ConversationHandler.END

async def show_cement(update, ctx):
    d = ctx.user_data["d"]; r = Calc.cement(d["a"])
    cp = db.get_material("cement")
    cost = r["cement_bags"]*(cp["price"] if cp else 85000)
    txt = (f"🏠 *نتیجه سیمان*\n\n"
           f"├ مساحت: {d['a']} m²\n"
           f"├ سیمان: {r['cement_bags']} کیسه\n"
           f"├ ماسه: {r['sand_tons']} تن\n\n"
           f"💰 *هزینه سیمان: {fmtp(cost)}*")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(update.effective_user.id, "cement", d, r)
    return ConversationHandler.END

async def show_tile(update, ctx):
    d = ctx.user_data["d"]; r = Calc.tile(d["l"], d["w"])
    tp = db.get_material("tile")
    cost = r["area"]*(tp["price"] if tp else 250000)
    txt = (f"📐 *نتیجه کاشی*\n\n"
           f"├ مساحت: {r['area']} m²\n"
           f"├ کاشی: {r['tiles_waste']} عدد\n"
           f"├ چسب: {r['adhesive_bags']} کیسه\n\n"
           f"💰 *هزینه: {fmtp(cost)}*")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(update.effective_user.id, "tile", d, r)
    return ConversationHandler.END

async def show_gypsum(update, ctx):
    d = ctx.user_data["d"]; r = Calc.gypsum(d["a"])
    gp = db.get_material("gypsum")
    cost = d["a"]*(gp["price"] if gp else 120000)
    txt = (f"🔧 *نتیجه گچ‌کاری*\n\n"
           f"├ مساحت: {d['a']} m²\n"
           f"├ گچ: {r['gypsum_bags']} کیسه\n\n"
           f"💰 *هزینه: {fmtp(cost)}*")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(update.effective_user.id, "gypsum", d, r)
    return ConversationHandler.END

async def show_water(update, ctx):
    d = ctx.user_data["d"]; r = Calc.waterproof(d["a"])
    wp = db.get_material("waterproofing")
    cost = d["a"]*(wp["price"] if wp else 180000)
    txt = (f"💧 *نتیجه عایق*\n\n"
           f"├ مساحت: {d['a']} m²\n"
           f"├ ایزوگام: {r['rolls']} رول\n"
           f"├ پرایمر: {r['primer_l']} لیتر\n\n"
           f"💰 *هزینه: {fmtp(cost)}*")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(update.effective_user.id, "water", d, r)
    return ConversationHandler.END

async def show_found(update, ctx):
    d = ctx.user_data["d"]; r = Calc.foundation(d["l"], d["w"], d["t"])
    rp = db.get_material("rebar"); cp = db.get_material("concrete")
    cost = r["rebar_waste"]*(rp["price"] if rp else 32000) + r["volume"]*(cp["price"] if cp else 1800000)
    txt = (f"📊 *نتیجه فونداسیون*\n\n"
           f"├ حجم: {r['volume']} m³\n"
           f"├ میلگرد: {fmt(r['rebar_waste'])} kg\n"
           f"├ سیمان: {r['cement_bags']} کیسه\n\n"
           f"💰 *هزینه: {fmtp(cost)}*")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(update.effective_user.id, "found", d, r)
    return ConversationHandler.END

async def show_col(update, ctx):
    d = ctx.user_data["d"]; r = Calc.column(d["cw"], d["cd"], d["ch"], d["crc"], d["crd"])
    rp = db.get_material("rebar"); cp = db.get_material("concrete")
    cost = r["total_rebar"]*(rp["price"] if rp else 32000) + r["concrete_vol"]*(cp["price"] if cp else 1800000)
    txt = (f"🏢 *نتیجه ستون*\n\n"
           f"├ ابعاد: {d['cw']*100:.0f}×{d['cd']*100:.0f}×{d['ch']}m\n"
           f"├ بتن: {r['concrete_vol']} m³\n"
           f"├ میلگرد: {r['total_rebar']} kg\n\n"
           f"💰 *هزینه: {fmtp(cost)}*")
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(update.effective_user.id, "col", d, r)
    return ConversationHandler.END

# ── ESTIMATION ──
async def est_entry(update: Update, ctx):
    q = update.callback_query; await q.answer()
    types = {"e_res":"مسکونی","e_com":"تجاری","e_ind":"صنعتی"}
    if q.data in types:
        ctx.user_data["et"] = types[q.data]
        await q.edit_message_text(f"🏗 برآورد {ctx.user_data['et']}\n\nمساحت هر طبقه (m²):", reply_markup=cancel_kb())
        return EA
    if q.data == "back_main":
        await q.edit_message_text("از منو انتخاب کنید 👇"); return ConversationHandler.END

async def est_area(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",","."))
        if v <= 0: raise ValueError
        ctx.user_data["ea"] = v
        await update.message.reply_text("تعداد طبقات:", reply_markup=cancel_kb()); return EF
    except: await update.message.reply_text("⚠️ عدد مثبت:"); return EA

async def est_floors(update: Update, ctx):
    try:
        v = int(update.message.text)
        if v <= 0: raise ValueError
        ctx.user_data["ef"] = v
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏗 فلزی", callback_data="s_steel"), InlineKeyboardButton("🏗 بتنی", callback_data="s_concrete")],
            [InlineKeyboardButton("🧱 بنایی", callback_data="s_masonry")]])
        await update.message.reply_text("نوع سازه:", reply_markup=kb); return ES
    except: await update.message.reply_text("⚠️ عدد صحیح:"); return EF

async def est_struct(update: Update, ctx):
    q = update.callback_query; await q.answer()
    ss = {"s_steel":"steel","s_concrete":"concrete","s_masonry":"masonry"}
    if q.data in ss:
        ctx.user_data["es"] = ss[q.data]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ اقتصادی", callback_data="q_economic")],
            [InlineKeyboardButton("⭐⭐ متوسط", callback_data="q_medium")],
            [InlineKeyboardButton("⭐⭐⭐ لوکس", callback_data="q_luxury")]])
        await q.edit_message_text("سطح کیفیت:", reply_markup=kb); return EQ

async def est_quality(update: Update, ctx):
    q = update.callback_query; await q.answer()
    qs = {"q_economic":"economic","q_medium":"medium","q_luxury":"luxury"}
    if q.data in qs:
        r = Calc.estimate(ctx.user_data["ea"], ctx.user_data["ef"], ctx.user_data["es"], qs[q.data])
        sn = {"steel":"فلزی","concrete":"بتنی","masonry":"بنایی"}
        qn = {"economic":"اقتصادی","medium":"متوسط","luxury":"لوکس"}
        bd = "\n".join(f"├ {k}: {fmtp(v)}" for k,v in r["breakdown"].items())
        txt = (f"💰 *برآورد هزینه ساخت*\n\n"
               f"├ نوع: {ctx.user_data['et']}\n"
               f"├ سازه: {sn[ctx.user_data['es']]}\n"
               f"├ کیفیت: {qn[qs[q.data]]}\n"
               f"├ مساحت کل: {fmt(r['total_area'])} m²\n"
               f"├ هر m²: {fmtp(r['cost_per_m2'])}\n\n"
               f"📊 *ریز هزینه:*\n{bd}\n\n"
               f"━━━━━━━━━━━━━━━\n"
               f"💰 *جمع کل: {fmtp(r['total_cost'])}*\n"
               f"━━━━━━━━━━━━━━━")
        await q.edit_message_text(txt, parse_mode="Markdown")
        db.save_calculation(update.effective_user.id, "est", ctx.user_data, r)
        return ConversationHandler.END

# ── MATERIALS ──
async def mat_cb(update: Update, ctx):
    q = update.callback_query; await q.answer()
    if q.data.startswith("m_"):
        cat = q.data[2:]
        mats = db.get_all_materials() if cat == "all" else db.get_materials_by_category(cat)
        if not mats:
            await q.edit_message_text("❌ موردی یافت نشد.", reply_markup=back_kb("back_mat")); return
        txt = f"📦 *{cat}*\n\n"
        for m in mats:
            txt += f"• {m['persian_name']}: {fmt(m['price'])} تومان/{m['unit']}\n"
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=back_kb("back_mat"))
    elif q.data == "back_mat":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧱 پایه", callback_data="m_مصالح پایه"), InlineKeyboardButton("🔩 فلزات", callback_data="m_فلزات")],
            [InlineKeyboardButton("🏗 بتن", callback_data="m_بتن"), InlineKeyboardButton("🎨 نازک‌کاری", callback_data="m_نازک‌کاری")],
            [InlineKeyboardButton("💧 عایق", callback_data="m_عایق"), InlineKeyboardButton("📋 همه", callback_data="m_all")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]])
        await q.edit_message_text("📦 دسته‌بندی:", reply_markup=kb)

# ── CONVERTER ──
async def conv_entry(update: Update, ctx):
    q = update.callback_query; await q.answer()
    convs = {"v_mf":"متر↔فوت","v_m2":"m²↔ft²","v_m3":"m³↔لیتر","v_kg":"kg↔lb"}
    if q.data in convs:
        ctx.user_data["cv"] = q.data
        await q.edit_message_text(f"📐 {convs[q.data]}\n\nعدد را وارد کنید:", reply_markup=cancel_kb())
        return CV

async def conv_val(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",","."))
        ct = ctx.user_data["cv"]
        r = ""
        if ct == "v_mf": r = f"{v} متر = {v*3.28084:.2f} فوت\n{v} فوت = {v/3.28084:.2f} متر"
        elif ct == "v_m2": r = f"{v} m² = {v*10.7639:.2f} ft²\n{v} ft² = {v/10.7639:.2f} m²"
        elif ct == "v_m3": r = f"{v} m³ = {v*1000:.1f} لیتر\n{v} لیتر = {v/1000:.4f} m³"
        elif ct == "v_kg": r = f"{v} kg = {v*2.20462:.2f} lb\n{v} lb = {v/2.20462:.2f} kg"
        await update.message.reply_text(f"📐 *نتیجه:*\n\n{r}", parse_mode="Markdown", reply_markup=main_kb())
        return ConversationHandler.END
    except: await update.message.reply_text("⚠️ عدد:"); return CV

# ── CANCEL ──
async def cancel(update: Update, ctx):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ لغو شد.")
    return ConversationHandler.END

# ── MAIN ──
def main():
    if not TOKEN:
        logger.error("BOT_TOKEN not set!"); return
    app = Application.builder().token(TOKEN).build()

    calc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(calc_entry, pattern="^c_|^back_main$")],
        states={
            L: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_l)],
            W: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_w)],
            H: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_h)],
            T: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_t)],
            AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_area)],
            COL_W: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_cw)],
            COL_D: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_cd)],
            COL_H: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ch)],
            COL_RC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_crc)],
            COL_RD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_crd)],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern="^cancel$")], per_message=False)

    est_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(est_entry, pattern="^e_|^back_main$")],
        states={
            EA: [MessageHandler(filters.TEXT & ~filters.COMMAND, est_area)],
            EF: [MessageHandler(filters.TEXT & ~filters.COMMAND, est_floors)],
            ES: [CallbackQueryHandler(est_struct, pattern="^s_")],
            EQ: [CallbackQueryHandler(est_quality, pattern="^q_")],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern="^cancel$")], per_message=False)

    conv_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(conv_entry, pattern="^v_")],
        states={CV: [MessageHandler(filters.TEXT & ~filters.COMMAND, conv_val)]},
        fallbacks=[CallbackQueryHandler(cancel, pattern="^cancel$")], per_message=False)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(calc_conv)
    app.add_handler(est_conv)
    app.add_handler(conv_conv)
    app.add_handler(CallbackQueryHandler(mat_cb, pattern="^m_|^back_mat$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))

    logger.info("🤖 Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
