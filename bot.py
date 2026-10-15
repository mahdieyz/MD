import os, logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters)
from database import Database
from calculations import Calc, fmt, fmtp

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
db = Database()
TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",")]

# States
L,W,H,T,AREA,COL_W,COL_D,COL_H,COL_RC,COL_RD = range(10)
EA,EF,ES,EQ = range(10,14)
CV = 14
AP_MAT_SEL, AP_MAT_PRICE, AP_MAT_NEW_NAME, AP_MAT_NEW_FA, AP_MAT_NEW_UNIT, AP_MAT_NEW_PRICE, AP_MAT_NEW_CAT = range(20,27)
AP_EST_SEL, AP_EST_PRICE = range(27,29)
AP_WELCOME, AP_HELP, AP_BROADCAST = range(29,32)
AP_DEL_SEL = range(32,33)

def main_kb():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🧮 محاسبه‌گر"), KeyboardButton("💰 برآورد هزینه")],
        [KeyboardButton("📦 قیمت مصالح"), KeyboardButton("📐 تبدیل واحد")],
        [KeyboardButton("📋 تاریخچه"), KeyboardButton("ℹ️ راهنما")],
    ], resize_keyboard=True)

def cancel_kb(): return InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel")]])
def back_kb(cd="back_main"): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=cd)]])

def is_admin(uid): return uid in ADMIN_IDS

# ── START ──
async def start(update: Update, ctx):
    u = update.effective_user
    db.add_user(u.id, u.username, u.first_name, u.last_name)
    msg = db.get_setting("welcome_msg").replace("{name}", u.first_name or "کاربر")
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_kb())

async def help_cmd(update: Update, ctx):
    await update.message.reply_text(db.get_setting("help_msg"), parse_mode="Markdown")

# ── ADMIN PANEL ──
async def admin_cmd(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ دسترسی ندارید"); return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار", callback_data="ap_stats")],
        [InlineKeyboardButton("💰 ویرایش قیمت مصالح", callback_data="ap_mat"), InlineKeyboardButton("➕ افزودن مصالح", callback_data="ap_mat_add")],
        [InlineKeyboardButton("🗑️ حذف مصالح", callback_data="ap_mat_del"), InlineKeyboardButton("🏗 قیمت برآورد", callback_data="ap_est")],
        [InlineKeyboardButton("📝 پیام خوش‌آمد", callback_data="ap_welcome"), InlineKeyboardButton("📝 پیام راهنما", callback_data="ap_help")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="ap_broadcast")],
        [InlineKeyboardButton("👥 لیست کاربران", callback_data="ap_users")],
    ])
    await update.message.reply_text("🔧 *پنل مدیریت*\n\nگزینه مورد نظر را انتخاب کنید:", parse_mode="Markdown", reply_markup=kb)

async def admin_cb(update: Update, ctx):
    q = update.callback_query; await q.answer()
    d = q.data

    if d == "ap_stats":
        s = db.get_stats()
        await q.edit_message_text(
            f"📊 *آمار ربات*\n\n├ 👥 کاربران: {s['total_users']}\n├ 🟢 فعال امروز: {s['active_today']}\n"
            f"├ 🧮 محاسبات: {s['total_calculations']}\n├ 📦 مصالح: {s['total_materials']}",
            parse_mode="Markdown", reply_markup=back_kb("ap_back"))

    elif d == "ap_mat":
        mats = db.get_all_materials()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{m['persian_name']} ({fmt(m['price'])})", callback_data=f"apm_{m['name']}")] for m in mats[:15]])
        kb.inline_keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="ap_back")])
        await q.edit_message_text("💰 مصالح را انتخاب کنید:", reply_markup=kb)

    elif d.startswith("apm_"):
        name = d[4:]; m = db.get_material(name)
        ctx.user_data["edit_mat"] = name
        await q.edit_message_text(
            f"📦 {m['persian_name']}\n├ قیمت فعلی: {fmt(m['price'])} تومان\n├ واحد: {m['unit']}\n├ دسته: {m['category']}\n\n"
            f"قیمت جدید را وارد کنید:", reply_markup=cancel_kb())
        return AP_MAT_PRICE

    elif d == "ap_mat_add":
        await q.edit_message_text("➕ نام انگلیسی مصالح را وارد کنید:\n(مثال: `cement`)", parse_mode="Markdown", reply_markup=cancel_kb())
        return AP_MAT_NEW_NAME

    elif d == "ap_mat_del":
        mats = db.get_all_materials()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🗑️ {m['persian_name']}", callback_data=f"apd_{m['name']}")] for m in mats[:15]])
        kb.inline_keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="ap_back")])
        await q.edit_message_text("🗑️ مصالح مورد نظر برای حذف:", reply_markup=kb)

    elif d.startswith("apd_"):
        name = d[4:]; m = db.get_material(name)
        db.delete_material(name)
        await q.edit_message_text(f"✅ {m['persian_name']} حذف شد.", reply_markup=back_kb("ap_back"))

    elif d == "ap_est":
        prices = db.get_all_est_prices()
        sn = {"steel":"فلزی","concrete":"بتنی","masonry":"بنایی"}
        qn = {"economic":"اقتصادی","medium":"متوسط","luxury":"لوکس"}
        txt = "🏗 *قیمت برآورد (هر m²)*\n\n"
        kb = []
        for p in prices:
            txt += f"├ {sn.get(p['structure'],p['structure'])} {qn.get(p['quality'],p['quality'])}: {fmtp(p['price'])}\n"
            kb.append([InlineKeyboardButton(f"{sn.get(p['structure'],'')} {qn.get(p['quality'],'')}", callback_data=f"ape_{p['structure']}_{p['quality']}")])
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="ap_back")])
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("ape_"):
        parts = d[4:].split("_")
        ctx.user_data["est_struct"] = parts[0]
        ctx.user_data["est_qual"] = parts[1]
        sn = {"steel":"فلزی","concrete":"بتنی","masonry":"بنایی"}
        qn = {"economic":"اقتصادی","medium":"متوسط","luxury":"لوکس"}
        cur = db.get_est_price(parts[0], parts[1])
        await q.edit_message_text(
            f"🏗 {sn.get(parts[0],'')} - {qn.get(parts[1],'')}\nقیمت فعلی: {fmtp(cur)}\n\nقیمت جدید (هر m²) را وارد کنید:",
            reply_markup=cancel_kb())
        return AP_EST_PRICE

    elif d == "ap_welcome":
        cur = db.get_setting("welcome_msg")
        await q.edit_message_text(f"📝 پیام خوش‌آمد فعلی:\n\n{cur[:200]}...\n\nپیام جدید را ارسال کنید:\n(از `{{name}}` برای نام کاربر استفاده کنید)", parse_mode="Markdown", reply_markup=cancel_kb())
        return AP_WELCOME

    elif d == "ap_help":
        await q.edit_message_text("📝 پیام راهنمای جدید را ارسال کنید:", reply_markup=cancel_kb())
        return AP_HELP

    elif d == "ap_broadcast":
        await q.edit_message_text("📢 متن پیام همگانی را ارسال کنید:", reply_markup=cancel_kb())
        return AP_BROADCAST

    elif d == "ap_users":
        users = db.get_all_users()
        txt = f"👥 *کاربران ({len(users)} نفر)*\n\n"
        for u in users[:20]:
            txt += f"• {u['first_name'] or '-'} (@{u['username'] or '-'}) - {u['calculation_count']} محاسبه\n"
        if len(users) > 20: txt += f"\n... و {len(users)-20} نفر دیگر"
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=back_kb("ap_back"))

    elif d == "ap_back":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 آمار", callback_data="ap_stats")],
            [InlineKeyboardButton("💰 ویرایش قیمت", callback_data="ap_mat"), InlineKeyboardButton("➕ افزودن", callback_data="ap_mat_add")],
            [InlineKeyboardButton("🗑️ حذف", callback_data="ap_mat_del"), InlineKeyboardButton("🏗 برآورد", callback_data="ap_est")],
            [InlineKeyboardButton("📝 خوش‌آمد", callback_data="ap_welcome"), InlineKeyboardButton("📝 راهنما", callback_data="ap_help")],
            [InlineKeyboardButton("📢 همگانی", callback_data="ap_broadcast")],
            [InlineKeyboardButton("👥 کاربران", callback_data="ap_users")],
        ])
        await q.edit_message_text("🔧 *پنل مدیریت*", parse_mode="Markdown", reply_markup=kb)

# ── ADMIN INPUT HANDLERS ──
async def ap_mat_price(update: Update, ctx):
    try:
        price = float(update.message.text.replace(",",""))
        name = ctx.user_data["edit_mat"]; m = db.get_material(name)
        db.update_material_price(name, price)
        await update.message.reply_text(f"✅ قیمت {m['persian_name']} به {fmt(price)} تومان تغییر کرد.", reply_markup=main_kb())
        return ConversationHandler.END
    except: await update.message.reply_text("⚠️ عدد وارد کنید:"); return AP_MAT_PRICE

async def ap_new_name(update: Update, ctx):
    ctx.user_data["new_mat_name"] = update.message.text.strip()
    await update.message.reply_text("نام فارسی را وارد کنید:\n(مثال: سیمان)", reply_markup=cancel_kb()); return AP_MAT_NEW_FA

async def ap_new_fa(update: Update, ctx):
    ctx.user_data["new_mat_fa"] = update.message.text.strip()
    await update.message.reply_text("واحد را وارد کنید:\n(مثال: کیسه، کیلوگرم، متر مربع)", reply_markup=cancel_kb()); return AP_MAT_NEW_UNIT

async def ap_new_unit(update: Update, ctx):
    ctx.user_data["new_mat_unit"] = update.message.text.strip()
    await update.message.reply_text("قیمت را وارد کنید:", reply_markup=cancel_kb()); return AP_MAT_NEW_PRICE

async def ap_new_price(update: Update, ctx):
    try:
        ctx.user_data["new_mat_price"] = float(update.message.text.replace(",",""))
        await update.message.reply_text("دسته‌بندی را وارد کنید:\n(مثال: مصالح پایه، فلزات، نازک‌کاری)", reply_markup=cancel_kb()); return AP_MAT_NEW_CAT
    except: await update.message.reply_text("⚠️ عدد:"); return AP_MAT_NEW_PRICE

async def ap_new_cat(update: Update, ctx):
    cat = update.message.text.strip()
    db.add_material(ctx.user_data["new_mat_name"], ctx.user_data["new_mat_fa"],
                    ctx.user_data["new_mat_unit"], ctx.user_data["new_mat_price"], cat)
    await update.message.reply_text(f"✅ {ctx.user_data['new_mat_fa']} اضافه شد!", reply_markup=main_kb())
    return ConversationHandler.END

async def ap_est_price(update: Update, ctx):
    try:
        price = float(update.message.text.replace(",",""))
        db.set_est_price(ctx.user_data["est_struct"], ctx.user_data["est_qual"], price)
        await update.message.reply_text(f"✅ قیمت برآورد تغییر کرد: {fmtp(price)}", reply_markup=main_kb())
        return ConversationHandler.END
    except: await update.message.reply_text("⚠️ عدد:"); return AP_EST_PRICE

async def ap_welcome_msg(update: Update, ctx):
    db.set_setting("welcome_msg", update.message.text)
    await update.message.reply_text("✅ پیام خوش‌آمد تغییر کرد!", reply_markup=main_kb())
    return ConversationHandler.END

async def ap_help_msg(update: Update, ctx):
    db.set_setting("help_msg", update.message.text)
    await update.message.reply_text("✅ پیام راهنما تغییر کرد!", reply_markup=main_kb())
    return ConversationHandler.END

async def ap_broadcast_msg(update: Update, ctx):
    msg = update.message.text; users = db.get_all_users()
    ok = 0; fail = 0
    for u in users:
        try:
            await ctx.bot.send_message(u["user_id"], f"📢 {msg}", parse_mode="Markdown"); ok += 1
        except: fail += 1
    await update.message.reply_text(f"✅ ارسال شد!\n├ موفق: {ok}\n├ ناموفق: {fail}", reply_markup=main_kb())
    return ConversationHandler.END

# ── MENU ──
async def menu(update: Update, ctx):
    t = update.message.text; db.update_activity(update.effective_user.id)
    if "محاسبه" in t:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧱 آجر", callback_data="c_brick"), InlineKeyboardButton("🏗 بتن", callback_data="c_concrete")],
            [InlineKeyboardButton("📏 میلگرد", callback_data="c_rebar"), InlineKeyboardButton("🎨 رنگ", callback_data="c_paint")],
            [InlineKeyboardButton("🏠 سیمان", callback_data="c_cement"), InlineKeyboardButton("📐 کاشی", callback_data="c_tile")],
            [InlineKeyboardButton("🔧 گچ", callback_data="c_gypsum"), InlineKeyboardButton("💧 عایق", callback_data="c_water")],
            [InlineKeyboardButton("📊 فونداسیون", callback_data="c_found"), InlineKeyboardButton("🏢 ستون", callback_data="c_col")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]])
        await update.message.reply_text("🧮 نوع محاسبه:", reply_markup=kb)
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
        if not calcs: await update.message.reply_text("📋 تاریخچه خالی است."); return
        names = {"brick":"🧱","concrete":"🏗","rebar":"📏","paint":"🎨","cement":"🏠","tile":"📐","gypsum":"🔧","water":"💧","found":"📊","col":"🏢","est":"💰"}
        txt = "📋 *۱۰ محاسبه آخر:*\n\n"
        for i, c in enumerate(calcs, 1): txt += f"{i}. {names.get(c['calc_type'],'')} {c['calc_type']} - {c['created_at'][:16]}\n"
        await update.message.reply_text(txt, parse_mode="Markdown")
    elif "راهنما" in t: await help_cmd(update, ctx)

# ── CALCULATOR ──
async def calc_entry(update: Update, ctx):
    q = update.callback_query; await q.answer()
    if q.data == "back_main": await q.edit_message_text("از منو انتخاب کنید 👇"); return ConversationHandler.END
    prompts = {
        "c_brick":("brick","طول اتاق (متر):",L), "c_concrete":("concrete","طول سطح (متر):",L),
        "c_rebar":("rebar","مساحت سقف (m²):",AREA), "c_paint":("paint","مساحت رنگ (m²):",AREA),
        "c_cement":("cement","مساحت سیمانکاری (m²):",AREA), "c_tile":("tile","طول کاشی (متر):",L),
        "c_gypsum":("gypsum","مساحت گچ (m²):",AREA), "c_water":("water","مساحت عایق (m²):",AREA),
        "c_found":("found","طول فونداسیون (متر):",L), "c_col":("col","عرض ستون (سانتیمتر):",COL_W),
    }
    if q.data in prompts:
        ct, prompt, state = prompts[q.data]; ctx.user_data["ct"] = ct; ctx.user_data["d"] = {}
        await q.edit_message_text(f"🧮 {prompt}", reply_markup=cancel_kb()); return state

async def get_l(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",",".")); ctx.user_data["d"]["l"] = v
        if ctx.user_data["ct"] in ("brick","concrete","found","tile"):
            await update.message.reply_text("عرض (متر):", reply_markup=cancel_kb()); return W
    except: await update.message.reply_text("⚠️ عدد مثبت:"); return L

async def get_w(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",",".")); ctx.user_data["d"]["w"] = v; ct = ctx.user_data["ct"]
        if ct == "brick": await update.message.reply_text("ارتفاع (متر):", reply_markup=cancel_kb()); return H
        elif ct in ("concrete","found"): await update.message.reply_text("ضخامت (متر):", reply_markup=cancel_kb()); return T
        elif ct == "tile": return await show_tile(update, ctx)
    except: await update.message.reply_text("⚠️ عدد:"); return W

async def get_h(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",",".")); ctx.user_data["d"]["h"] = v
        if ctx.user_data["ct"] == "brick": return await show_brick(update, ctx)
    except: await update.message.reply_text("⚠️ عدد:"); return H

async def get_t(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",",".")); ctx.user_data["d"]["t"] = v
        if ctx.user_data["ct"] == "concrete": return await show_concrete(update, ctx)
        elif ctx.user_data["ct"] == "found": return await show_found(update, ctx)
    except: await update.message.reply_text("⚠️ عدد:"); return T

async def get_area(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",",".")); ctx.user_data["d"]["a"] = v; ct = ctx.user_data["ct"]
        if ct == "rebar": return await show_rebar(update, ctx)
        elif ct == "paint": return await show_paint(update, ctx)
        elif ct == "cement": return await show_cement(update, ctx)
        elif ct == "gypsum": return await show_gypsum(update, ctx)
        elif ct == "water": return await show_water(update, ctx)
    except: await update.message.reply_text("⚠️ عدد:"); return AREA

async def get_cw(update: Update, ctx):
    try: ctx.user_data["d"]["cw"] = float(update.message.text)/100; await update.message.reply_text("عمق (cm):", reply_markup=cancel_kb()); return COL_D
    except: await update.message.reply_text("⚠️ عدد:"); return COL_W
async def get_cd(update: Update, ctx):
    try: ctx.user_data["d"]["cd"] = float(update.message.text)/100; await update.message.reply_text("ارتفاع (متر):", reply_markup=cancel_kb()); return COL_H
    except: await update.message.reply_text("⚠️ عدد:"); return COL_D
async def get_ch(update: Update, ctx):
    try: ctx.user_data["d"]["ch"] = float(update.message.text); await update.message.reply_text("تعداد میلگرد:", reply_markup=cancel_kb()); return COL_RC
    except: await update.message.reply_text("⚠️ عدد:"); return COL_H
async def get_crc(update: Update, ctx):
    try: ctx.user_data["d"]["crc"] = int(update.message.text); await update.message.reply_text("قطر میلگرد (mm):", reply_markup=cancel_kb()); return COL_RD
    except: await update.message.reply_text("⚠️ عدد:"); return COL_RC
async def get_crd(update: Update, ctx):
    try: ctx.user_data["d"]["crd"] = int(update.message.text); return await show_col(update, ctx)
    except: await update.message.reply_text("⚠️ عدد:"); return COL_RD

# ── RESULTS ──
def gp(name, default): m = db.get_material(name); return m["price"] if m else default

async def show_brick(u, ctx):
    d = ctx.user_data["d"]; r = Calc.brick(d["l"],d["w"],d["h"])
    cost = r["waste"]*gp("brick",1200) + r["cement_bags"]*gp("cement",85000)
    await u.message.reply_text(f"🧱 *آجرچینی*\n├ آجر: {fmt(r['waste'])} عدد\n├ سیمان: {r['cement_bags']} کیسه\n├ ماسه: {r['sand_tons']} تن\n\n💰 *{fmtp(cost)}*", parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(u.effective_user.id,"brick",d,r); return ConversationHandler.END

async def show_concrete(u, ctx):
    d = ctx.user_data["d"]; r = Calc.concrete(d["l"],d["w"],d["t"])
    cost = r["volume_waste"]*gp("concrete",1800000)
    await u.message.reply_text(f"🏗 *بتن*\n├ حجم: {r['volume_waste']} m³\n├ سیمان: {r['cement_bags']} کیسه\n├ ماسه: {fmt(r['sand_kg'])} kg\n├ شن: {fmt(r['gravel_kg'])} kg\n\n💰 *{fmtp(cost)}*", parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(u.effective_user.id,"concrete",d,r); return ConversationHandler.END

async def show_rebar(u, ctx):
    d = ctx.user_data["d"]; r = Calc.rebar(d["a"]); cost = r["rebar_waste"]*gp("rebar",32000)
    await u.message.reply_text(f"📏 *میلگرد*\n├ {fmt(r['rebar_waste'])} kg\n\n💰 *{fmtp(cost)}*", parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(u.effective_user.id,"rebar",d,r); return ConversationHandler.END

async def show_paint(u, ctx):
    d = ctx.user_data["d"]; r = Calc.paint(d["a"]); cost = d["a"]*gp("paint",45000)
    await u.message.reply_text(f"🎨 *رنگ*\n├ {r['waste_liters']} لیتر\n├ {r['gallon_4l']} قوطی\n\n💰 *{fmtp(cost)}*", parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(u.effective_user.id,"paint",d,r); return ConversationHandler.END

async def show_cement(u, ctx):
    d = ctx.user_data["d"]; r = Calc.cement(d["a"]); cost = r["cement_bags"]*gp("cement",85000)
    await u.message.reply_text(f"🏠 *سیمان*\n├ {r['cement_bags']} کیسه\n├ ماسه: {r['sand_tons']} تن\n\n💰 *{fmtp(cost)}*", parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(u.effective_user.id,"cement",d,r); return ConversationHandler.END

async def show_tile(u, ctx):
    d = ctx.user_data["d"]; r = Calc.tile(d["l"],d["w"]); cost = r["area"]*gp("tile",250000)
    await u.message.reply_text(f"📐 *کاشی*\n├ {r['tiles_waste']} عدد\n├ چسب: {r['adhesive_bags']} کیسه\n\n💰 *{fmtp(cost)}*", parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(u.effective_user.id,"tile",d,r); return ConversationHandler.END

async def show_gypsum(u, ctx):
    d = ctx.user_data["d"]; r = Calc.gypsum(d["a"]); cost = d["a"]*gp("gypsum",120000)
    await u.message.reply_text(f"🔧 *گچ*\n├ {r['gypsum_bags']} کیسه\n\n💰 *{fmtp(cost)}*", parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(u.effective_user.id,"gypsum",d,r); return ConversationHandler.END

async def show_water(u, ctx):
    d = ctx.user_data["d"]; r = Calc.waterproof(d["a"]); cost = d["a"]*gp("waterproofing",180000)
    await u.message.reply_text(f"💧 *عایق*\n├ {r['rolls']} رول\n├ پرایمر: {r['primer_l']} لیتر\n\n💰 *{fmtp(cost)}*", parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(u.effective_user.id,"water",d,r); return ConversationHandler.END

async def show_found(u, ctx):
    d = ctx.user_data["d"]; r = Calc.foundation(d["l"],d["w"],d["t"])
    cost = r["rebar_waste"]*gp("rebar",32000) + r["volume"]*gp("concrete",1800000)
    await u.message.reply_text(f"📊 *فونداسیون*\n├ {r['volume']} m³\n├ میلگرد: {fmt(r['rebar_waste'])} kg\n\n💰 *{fmtp(cost)}*", parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(u.effective_user.id,"found",d,r); return ConversationHandler.END

async def show_col(u, ctx):
    d = ctx.user_data["d"]; r = Calc.column(d["cw"],d["cd"],d["ch"],d["crc"],d["crd"])
    cost = r["total_rebar"]*gp("rebar",32000) + r["concrete_vol"]*gp("concrete",1800000)
    await u.message.reply_text(f"🏢 *ستون*\n├ بتن: {r['concrete_vol']} m³\n├ میلگرد: {r['total_rebar']} kg\n\n💰 *{fmtp(cost)}*", parse_mode="Markdown", reply_markup=main_kb())
    db.save_calculation(u.effective_user.id,"col",d,r); return ConversationHandler.END

# ── ESTIMATION ──
async def est_entry(update: Update, ctx):
    q = update.callback_query; await q.answer()
    types = {"e_res":"مسکونی","e_com":"تجاری","e_ind":"صنعتی"}
    if q.data in types:
        ctx.user_data["et"] = types[q.data]
        await q.edit_message_text(f"🏗 {ctx.user_data['et']}\nمساحت هر طبقه (m²):", reply_markup=cancel_kb()); return EA
    if q.data == "back_main": await q.edit_message_text("از منو انتخاب کنید 👇"); return ConversationHandler.END

async def est_area(update: Update, ctx):
    try: ctx.user_data["ea"] = float(update.message.text.replace(",",".")); await update.message.reply_text("تعداد طبقات:", reply_markup=cancel_kb()); return EF
    except: await update.message.reply_text("⚠️ عدد:"); return EA

async def est_floors(update: Update, ctx):
    try:
        ctx.user_data["ef"] = int(update.message.text)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏗 فلزی",callback_data="s_steel"),InlineKeyboardButton("🏗 بتنی",callback_data="s_concrete")],[InlineKeyboardButton("🧱 بنایی",callback_data="s_masonry")]])
        await update.message.reply_text("نوع سازه:", reply_markup=kb); return ES
    except: await update.message.reply_text("⚠️ عدد:"); return EF

async def est_struct(update: Update, ctx):
    q = update.callback_query; await q.answer()
    ss = {"s_steel":"steel","s_concrete":"concrete","s_masonry":"masonry"}
    if q.data in ss:
        ctx.user_data["es"] = ss[q.data]
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⭐ اقتصادی",callback_data="q_economic")],[InlineKeyboardButton("⭐⭐ متوسط",callback_data="q_medium")],[InlineKeyboardButton("⭐⭐⭐ لوکس",callback_data="q_luxury")]])
        await q.edit_message_text("کیفیت:", reply_markup=kb); return EQ

async def est_quality(update: Update, ctx):
    q = update.callback_query; await q.answer()
    qs = {"q_economic":"economic","q_medium":"medium","q_luxury":"luxury"}
    if q.data in qs:
        qual = qs[q.data]; area = ctx.user_data["ea"]; floors = ctx.user_data["ef"]; struct = ctx.user_data["es"]
        cpm = db.get_est_price(struct, qual); ta = area * floors; tc = ta * cpm
        bd = {"🏗 اسکلت":0.30,"🏗 فونداسیون":0.10,"🧱 دیوار":0.10,"🎨 نازک‌کاری":0.20,"🔧 مکانیکی":0.12,"⚡ برقی":0.08,"📋 متفرقه":0.10}
        sn = {"steel":"فلزی","concrete":"بتنی","masonry":"بنایی"}; qn = {"economic":"اقتصادی","medium":"متوسط","luxury":"لوکس"}
        bdt = "\n".join(f"├ {k}: {fmtp(tc*v)}" for k,v in bd.items())
        txt = f"💰 *برآورد*\n├ {ctx.user_data['et']} | {sn[struct]} | {qn[qual]}\n├ مساحت: {fmt(ta)} m²\n├ هر m²: {fmtp(cpm)}\n\n{bdt}\n\n💰 *جمع: {fmtp(tc)}*"
        await q.edit_message_text(txt, parse_mode="Markdown")
        db.save_calculation(update.effective_user.id,"est",ctx.user_data,{"total":tc}); return ConversationHandler.END

# ── MATERIALS ──
async def mat_cb(update: Update, ctx):
    q = update.callback_query; await q.answer()
    if q.data.startswith("m_"):
        cat = q.data[2:]; mats = db.get_all_materials() if cat == "all" else db.get_materials_by_category(cat)
        if not mats: await q.edit_message_text("❌ خالی", reply_markup=back_kb("back_mat")); return
        txt = f"📦 *{cat}*\n\n" + "\n".join(f"• {m['persian_name']}: {fmt(m['price'])} تومان/{m['unit']}" for m in mats)
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=back_kb("back_mat"))
    elif q.data == "back_mat":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🧱 پایه",callback_data="m_مصالح پایه"),InlineKeyboardButton("🔩 فلزات",callback_data="m_فلزات")],[InlineKeyboardButton("🏗 بتن",callback_data="m_بتن"),InlineKeyboardButton("🎨 نازک",callback_data="m_نازک‌کاری")],[InlineKeyboardButton("💧 عایق",callback_data="m_عایق"),InlineKeyboardButton("📋 همه",callback_data="m_all")],[InlineKeyboardButton("🔙 بازگشت",callback_data="back_main")]])
        await q.edit_message_text("📦 دسته‌بندی:", reply_markup=kb)

# ── CONVERTER ──
async def conv_entry(update: Update, ctx):
    q = update.callback_query; await q.answer()
    convs = {"v_mf":"متر↔فوت","v_m2":"m²↔ft²","v_m3":"m³↔لیتر","v_kg":"kg↔lb"}
    if q.data in convs: ctx.user_data["cv"] = q.data; await q.edit_message_text(f"📐 {convs[q.data]}\nعدد:", reply_markup=cancel_kb()); return CV

async def conv_val(update: Update, ctx):
    try:
        v = float(update.message.text.replace(",",".")); ct = ctx.user_data["cv"]; r = ""
        if ct == "v_mf": r = f"{v} متر = {v*3.28084:.2f} فوت\n{v} فوت = {v/3.28084:.2f} متر"
        elif ct == "v_m2": r = f"{v} m² = {v*10.7639:.2f} ft²"
        elif ct == "v_m3": r = f"{v} m³ = {v*1000:.1f} لیتر"
        elif ct == "v_kg": r = f"{v} kg = {v*2.20462:.2f} lb"
        await update.message.reply_text(f"📐 *{r}*", parse_mode="Markdown", reply_markup=main_kb()); return ConversationHandler.END
    except: await update.message.reply_text("⚠️ عدد:"); return CV

# ── CANCEL ──
async def cancel(update: Update, ctx):
    if update.callback_query: await update.callback_query.answer(); await update.callback_query.edit_message_text("❌ لغو")
    return ConversationHandler.END

# ── MAIN ──
def main():
    if not TOKEN: return
    app = Application.builder().token(TOKEN).build()

    calc_conv = ConversationHandler(entry_points=[CallbackQueryHandler(calc_entry, pattern="^c_|^back_main$")],
        states={L:[MessageHandler(filters.TEXT&~filters.COMMAND,get_l)],W:[MessageHandler(filters.TEXT&~filters.COMMAND,get_w)],
                H:[MessageHandler(filters.TEXT&~filters.COMMAND,get_h)],T:[MessageHandler(filters.TEXT&~filters.COMMAND,get_t)],
                AREA:[MessageHandler(filters.TEXT&~filters.COMMAND,get_area)],
                COL_W:[MessageHandler(filters.TEXT&~filters.COMMAND,get_cw)],COL_D:[MessageHandler(filters.TEXT&~filters.COMMAND,get_cd)],
                COL_H:[MessageHandler(filters.TEXT&~filters.COMMAND,get_ch)],COL_RC:[MessageHandler(filters.TEXT&~filters.COMMAND,get_crc)],
                COL_RD:[MessageHandler(filters.TEXT&~filters.COMMAND,get_crd)]},
        fallbacks=[CallbackQueryHandler(cancel,pattern="^cancel$")], per_message=False)

    est_conv = ConversationHandler(entry_points=[CallbackQueryHandler(est_entry, pattern="^e_|^back_main$")],
        states={EA:[MessageHandler(filters.TEXT&~filters.COMMAND,est_area)],EF:[MessageHandler(filters.TEXT&~filters.COMMAND,est_floors)],
                ES:[CallbackQueryHandler(est_struct,pattern="^s_")],EQ:[CallbackQueryHandler(est_quality,pattern="^q_")]},
        fallbacks=[CallbackQueryHandler(cancel,pattern="^cancel$")], per_message=False)

    conv_conv = ConversationHandler(entry_points=[CallbackQueryHandler(conv_entry, pattern="^v_")],
        states={CV:[MessageHandler(filters.TEXT&~filters.COMMAND,conv_val)]},
        fallbacks=[CallbackQueryHandler(cancel,pattern="^cancel$")], per_message=False)

    admin_conv = ConversationHandler(entry_points=[CallbackQueryHandler(admin_cb, pattern="^ap_|^apm_|^apd_|^ape_")],
        states={
            AP_MAT_PRICE:[MessageHandler(filters.TEXT&~filters.COMMAND,ap_mat_price)],
            AP_MAT_NEW_NAME:[MessageHandler(filters.TEXT&~filters.COMMAND,ap_new_name)],
            AP_MAT_NEW_FA:[MessageHandler(filters.TEXT&~filters.COMMAND,ap_new_fa)],
            AP_MAT_NEW_UNIT:[MessageHandler(filters.TEXT&~filters.COMMAND,ap_new_unit)],
            AP_MAT_NEW_PRICE:[MessageHandler(filters.TEXT&~filters.COMMAND,ap_new_price)],
            AP_MAT_NEW_CAT:[MessageHandler(filters.TEXT&~filters.COMMAND,ap_new_cat)],
            AP_EST_PRICE:[MessageHandler(filters.TEXT&~filters.COMMAND,ap_est_price)],
            AP_WELCOME:[MessageHandler(filters.TEXT&~filters.COMMAND,ap_welcome_msg)],
            AP_HELP:[MessageHandler(filters.TEXT&~filters.COMMAND,ap_help_msg)],
            AP_BROADCAST:[MessageHandler(filters.TEXT&~filters.COMMAND,ap_broadcast_msg)],
        },
        fallbacks=[CallbackQueryHandler(cancel,pattern="^cancel$")], per_message=False)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(calc_conv)
    app.add_handler(est_conv)
    app.add_handler(conv_conv)
    app.add_handler(admin_conv)
    app.add_handler(CallbackQueryHandler(mat_cb, pattern="^m_|^back_mat$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))
    logging.info("🤖 Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
