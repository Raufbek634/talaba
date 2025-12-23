"""
🎓 TalabaLife Bot - Bitta Fayl
Talabalar uchun kvartira, ish va eslatmalar boti

ISHGA TUSHIRISH:
1. pip install aiogram apscheduler
2. BOT_TOKEN ni o'zgartiring
3. python bot.py

Ma'lumotlar JSON faylda saqlanadi!
"""

import asyncio
import logging
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ========== SOZLAMALAR ==========
BOT_TOKEN = "8534425696:AAGOfUBWbwTNPFHVAWjYg5WS27BvoSK1noc"  # BU YERGA TOKEN!
ADMIN_IDS = [6439945348]  # Admin ID lar
DATA_FILE = "data.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== DATABASE ==========
class DB:
    def __init__(self):
        self.data = self.load()

    def load(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"users": {}, "apartments": [], "jobs": [], "reminders": [], "ids": {"apt": 1, "job": 1, "rem": 1}}

    def save(self):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_user(self, uid, name):
        if str(uid) not in self.data["users"]:
            self.data["users"][str(uid)] = {"id": uid, "name": name, "created": datetime.now().isoformat()}
            self.save()

    def add_apt(self, uid, region, district, rooms, price, desc, contact, photos=""):
        apt_id = self.data["ids"]["apt"]
        self.data["ids"]["apt"] += 1
        self.data["apartments"].append({
            "id": apt_id, "owner": uid, "region": region, "district": district,
            "rooms": rooms, "price": price, "desc": desc, "contact": contact,
            "photos": photos, "approved": False, "vip": False, "views": 0,
            "created": datetime.now().isoformat()
        })
        self.save()
        return apt_id

    def add_job(self, uid, title, job_type, region, salary, desc, contact):
        job_id = self.data["ids"]["job"]
        self.data["ids"]["job"] += 1
        self.data["jobs"].append({
            "id": job_id, "owner": uid, "title": title, "type": job_type,
            "region": region, "salary": salary, "desc": desc, "contact": contact,
            "approved": False, "vip": False, "views": 0, "created": datetime.now().isoformat()
        })
        self.save()
        return job_id

    def add_reminder(self, uid, title, rtype, remind_at):
        rem_id = self.data["ids"]["rem"]
        self.data["ids"]["rem"] += 1
        self.data["reminders"].append({
            "id": rem_id, "user": uid, "title": title, "type": rtype,
            "remind_at": remind_at, "sent": False, "created": datetime.now().isoformat()
        })
        self.save()
        return rem_id

    def get_apts(self, region=None, rooms=None, price_min=0, price_max=999999999):
        apts = [a for a in self.data["apartments"] if a["approved"]]
        if region:
            apts = [a for a in apts if a["region"] == region]
        if rooms:
            apts = [a for a in apts if a["rooms"] == rooms]
        apts = [a for a in apts if price_min <= a["price"] <= price_max]
        return sorted(apts, key=lambda x: (-x["vip"], -x["id"]))[:20]

    def get_jobs(self, region=None, job_type=None):
        jobs = [j for j in self.data["jobs"] if j["approved"]]
        if region:
            jobs = [j for j in jobs if j["region"] == region]
        if job_type:
            jobs = [j for j in jobs if j["type"] == job_type]
        return sorted(jobs, key=lambda x: (-x["vip"], -x["id"]))[:20]

    def get_pending_apts(self):
        return [a for a in self.data["apartments"] if not a["approved"]]

    def get_pending_jobs(self):
        return [j for j in self.data["jobs"] if not j["approved"]]

    def approve_apt(self, apt_id):
        for a in self.data["apartments"]:
            if a["id"] == apt_id:
                a["approved"] = True
                self.save()
                return True
        return False

    def approve_job(self, job_id):
        for j in self.data["jobs"]:
            if j["id"] == job_id:
                j["approved"] = True
                self.save()
                return True
        return False

    def set_vip_apt(self, apt_id):
        for a in self.data["apartments"]:
            if a["id"] == apt_id:
                a["vip"] = True
                self.save()
                return True
        return False

    def get_user_reminders(self, uid):
        return [r for r in self.data["reminders"] if r["user"] == uid and not r["sent"]]

    def get_pending_reminders(self):
        now = datetime.now()
        return [r for r in self.data["reminders"]
                if not r["sent"] and datetime.fromisoformat(r["remind_at"]) <= now]

    def mark_sent(self, rem_id):
        for r in self.data["reminders"]:
            if r["id"] == rem_id:
                r["sent"] = True
                self.save()
                break


db = DB()


# ========== FSM ==========
class AptStates(StatesGroup):
    region = State()
    district = State()
    rooms = State()
    price = State()
    desc = State()
    contact = State()
    photos = State()


class JobStates(StatesGroup):
    title = State()
    job_type = State()
    region = State()
    salary = State()
    desc = State()
    contact = State()


class RemStates(StatesGroup):
    title = State()
    rtype = State()
    date = State()
    time = State()


class SearchAptStates(StatesGroup):
    region = State()
    price = State()
    rooms = State()


class SearchJobStates(StatesGroup):
    region = State()
    job_type = State()


# ========== KEYBOARDS ==========
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏠 Kvartira"), KeyboardButton(text="💼 Ish")],
        [KeyboardButton(text="📅 Eslatma"), KeyboardButton(text="📊 Stats")]
    ], resize_keyboard=True)


def apt_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Qidirish"), KeyboardButton(text="➕ E'lon")],
        [KeyboardButton(text="🔙 Orqaga")]
    ], resize_keyboard=True)


def job_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Ish qidirish"), KeyboardButton(text="➕ Ish e'loni")],
        [KeyboardButton(text="🔙 Orqaga")]
    ], resize_keyboard=True)


def rem_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Yangi"), KeyboardButton(text="📋 Ro'yxat")],
        [KeyboardButton(text="🔙 Orqaga")]
    ], resize_keyboard=True)


REGIONS = ["Toshkent shahri", "Toshkent viloyati", "Andijon", "Buxoro", "Jizzax",
           "Qashqadaryo", "Namangan", "Samarqand", "Farg'ona"]


def region_kb():
    kb = [[KeyboardButton(text=REGIONS[i]), KeyboardButton(text=REGIONS[i + 1])]
          for i in range(0, len(REGIONS), 2)]
    kb.append([KeyboardButton(text="🔙 Bekor")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


# ========== BOT ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
scheduler = AsyncIOScheduler()


# ========== HANDLERS ==========
@router.message(Command("start"))
async def start(msg: Message):
    db.add_user(msg.from_user.id, msg.from_user.full_name)
    await msg.answer(
        f"🎓 <b>TalabaLife Bot</b>ga xush kelibsiz!\n\n"
        f"Salom, {msg.from_user.full_name}!\n\n"
        f"🏠 Kvartira topish\n💼 Part-time ish\n📅 Eslatmalar",
        reply_markup=main_kb(), parse_mode="HTML"
    )


# ===== KVARTIRA =====
@router.message(F.text == "🏠 Kvartira")
async def apt_menu(msg: Message):
    await msg.answer("🏠 Kvartira bo'limi", reply_markup=apt_kb())


@router.message(F.text == "🔍 Qidirish")
async def search_apt(msg: Message, state: FSMContext):
    await state.set_state(SearchAptStates.region)
    await msg.answer("📍 Viloyat tanlang:", reply_markup=region_kb())


@router.message(SearchAptStates.region)
async def search_apt_region(msg: Message, state: FSMContext):
    if msg.text == "🔙 Bekor":
        await state.clear()
        await msg.answer("Bekor qilindi", reply_markup=apt_kb())
        return
    await state.update_data(region=msg.text)
    await state.set_state(SearchAptStates.price)
    await msg.answer(
        "💰 Narx:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="100-300 ming"), KeyboardButton(text="300-500 ming")],
            [KeyboardButton(text="500-1 mln"), KeyboardButton(text="Farqi yo'q")]
        ], resize_keyboard=True)
    )


@router.message(SearchAptStates.price)
async def search_apt_price(msg: Message, state: FSMContext):
    await state.update_data(price=msg.text)
    await state.set_state(SearchAptStates.rooms)
    await msg.answer(
        "🚪 Xonalar:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2")],
            [KeyboardButton(text="3"), KeyboardButton(text="Farqi yo'q")]
        ], resize_keyboard=True)
    )


@router.message(SearchAptStates.rooms)
async def search_apt_rooms(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    price_map = {"100-300 ming": (100000, 300000), "300-500 ming": (300000, 500000),
                 "500-1 mln": (500000, 1000000), "Farqi yo'q": (0, 999999999)}
    pmin, pmax = price_map.get(data["price"], (0, 999999999))

    rooms = None if msg.text == "Farqi yo'q" else int(msg.text)
    apts = db.get_apts(data["region"], rooms, pmin, pmax)

    if not apts:
        await msg.answer("❌ Topilmadi", reply_markup=apt_kb())
        return

    await msg.answer(f"✅ {len(apts)} ta topildi!", reply_markup=apt_kb())

    for a in apts:
        vip = "⭐ VIP " if a["vip"] else ""
        text = f"{vip}<b>🏠 {a['rooms']} xonali</b>\n\n"
        text += f"📍 {a['region']}, {a['district']}\n"
        text += f"💰 {a['price']:,.0f} so'm/oy\n\n"
        text += f"📝 {a['desc']}\n\n"
        text += f"☎️ {a['contact']}\n"
        text += f"👁 {a['views']} | 📅 {a['created'][:10]}"

        if a["photos"]:
            try:
                await bot.send_photo(msg.chat.id, a["photos"].split(',')[0], caption=text, parse_mode="HTML")
            except:
                await msg.answer(text, parse_mode="HTML")
        else:
            await msg.answer(text, parse_mode="HTML")
        await asyncio.sleep(0.3)


@router.message(F.text == "➕ E'lon")
async def add_apt(msg: Message, state: FSMContext):
    await state.set_state(AptStates.region)
    await msg.answer("📍 Viloyat:", reply_markup=region_kb())


@router.message(AptStates.region)
async def add_apt_region(msg: Message, state: FSMContext):
    if msg.text == "🔙 Bekor":
        await state.clear()
        await msg.answer("Bekor", reply_markup=apt_kb())
        return
    await state.update_data(region=msg.text)
    await state.set_state(AptStates.district)
    await msg.answer("🏘 Tuman/shahar:", reply_markup=ReplyKeyboardRemove())


@router.message(AptStates.district)
async def add_apt_district(msg: Message, state: FSMContext):
    await state.update_data(district=msg.text)
    await state.set_state(AptStates.rooms)
    await msg.answer("🚪 Xonalar soni (1-4):")


@router.message(AptStates.rooms)
async def add_apt_rooms(msg: Message, state: FSMContext):
    try:
        rooms = int(msg.text)
        await state.update_data(rooms=rooms)
        await state.set_state(AptStates.price)
        await msg.answer("💰 Narx (so'mda):")
    except:
        await msg.answer("❌ Raqam kiriting!")


@router.message(AptStates.price)
async def add_apt_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.replace(' ', ''))
        await state.update_data(price=price)
        await state.set_state(AptStates.desc)
        await msg.answer("📝 Tavsif:")
    except:
        await msg.answer("❌ To'g'ri narx kiriting!")


@router.message(AptStates.desc)
async def add_apt_desc(msg: Message, state: FSMContext):
    await state.update_data(desc=msg.text)
    await state.set_state(AptStates.contact)
    await msg.answer("☎️ Telefon:")


@router.message(AptStates.contact)
async def add_apt_contact(msg: Message, state: FSMContext):
    await state.update_data(contact=msg.text)
    await state.set_state(AptStates.photos)
    await msg.answer(
        "📸 Rasm yuboring yoki 'Tayyor' bosing:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ Tayyor")]], resize_keyboard=True)
    )


@router.message(AptStates.photos, F.photo)
async def add_apt_photo(msg: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get('photos', [])
    photos.append(msg.photo[-1].file_id)
    await state.update_data(photos=photos)
    await msg.answer(f"✅ Qabul qilindi ({len(photos)})")


@router.message(AptStates.photos, F.text == "✅ Tayyor")
async def add_apt_finish(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    photos = ','.join(data.get('photos', []))
    apt_id = db.add_apt(msg.from_user.id, data['region'], data['district'],
                        data['rooms'], data['price'], data['desc'], data['contact'], photos)

    await msg.answer("✅ E'lon yuborildi!\nAdmin tasdiqlashi kutilmoqda.", reply_markup=apt_kb())

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id,
                                   f"🆕 Yangi kvartira #{apt_id}\n"
                                   f"Foydalanuvchi: {msg.from_user.full_name}\n"
                                   f"{data['rooms']} xonali - {data['region']}\n"
                                   f"Tasdiqlash: /approve_apt_{apt_id}")
        except:
            pass


# ===== ISH =====
@router.message(F.text == "💼 Ish")
async def job_menu(msg: Message):
    await msg.answer("💼 Ish bo'limi", reply_markup=job_kb())


@router.message(F.text == "🔍 Ish qidirish")
async def search_job(msg: Message, state: FSMContext):
    await state.set_state(SearchJobStates.region)
    await msg.answer("📍 Viloyat:", reply_markup=region_kb())


@router.message(SearchJobStates.region)
async def search_job_region(msg: Message, state: FSMContext):
    if msg.text == "🔙 Bekor":
        await state.clear()
        await msg.answer("Bekor", reply_markup=job_kb())
        return
    await state.update_data(region=msg.text)
    await state.set_state(SearchJobStates.job_type)
    await msg.answer(
        "💼 Ish turi:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Soatbay"), KeyboardButton(text="Masofaviy")],
            [KeyboardButton(text="Part-time"), KeyboardButton(text="Farqi yo'q")]
        ], resize_keyboard=True)
    )


@router.message(SearchJobStates.job_type)
async def search_job_type(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    jtype = None if msg.text == "Farqi yo'q" else msg.text
    jobs = db.get_jobs(data["region"], jtype)

    if not jobs:
        await msg.answer("❌ Topilmadi", reply_markup=job_kb())
        return

    await msg.answer(f"✅ {len(jobs)} ta topildi!", reply_markup=job_kb())

    for j in jobs:
        vip = "⭐ VIP " if j["vip"] else ""
        text = f"{vip}<b>💼 {j['title']}</b>\n\n"
        text += f"📍 {j['region']}\n"
        text += f"💰 {j['salary']}\n"
        text += f"🕐 {j['type']}\n\n"
        text += f"📝 {j['desc']}\n\n"
        text += f"☎️ {j['contact']}"
        await msg.answer(text, parse_mode="HTML")
        await asyncio.sleep(0.3)


@router.message(F.text == "➕ Ish e'loni")
async def add_job(msg: Message, state: FSMContext):
    await state.set_state(JobStates.title)
    await msg.answer("📝 Ish nomi:", reply_markup=ReplyKeyboardRemove())


@router.message(JobStates.title)
async def add_job_title(msg: Message, state: FSMContext):
    await state.update_data(title=msg.text)
    await state.set_state(JobStates.job_type)
    await msg.answer(
        "💼 Turi:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Soatbay"), KeyboardButton(text="Masofaviy")],
            [KeyboardButton(text="Part-time")]
        ], resize_keyboard=True)
    )


@router.message(JobStates.job_type)
async def add_job_type(msg: Message, state: FSMContext):
    await state.update_data(job_type=msg.text)
    await state.set_state(JobStates.region)
    await msg.answer("📍 Viloyat:", reply_markup=region_kb())


@router.message(JobStates.region)
async def add_job_region(msg: Message, state: FSMContext):
    await state.update_data(region=msg.text)
    await state.set_state(JobStates.salary)
    await msg.answer("💰 Maosh:", reply_markup=ReplyKeyboardRemove())


@router.message(JobStates.salary)
async def add_job_salary(msg: Message, state: FSMContext):
    await state.update_data(salary=msg.text)
    await state.set_state(JobStates.desc)
    await msg.answer("📝 Tavsif:")


@router.message(JobStates.desc)
async def add_job_desc(msg: Message, state: FSMContext):
    await state.update_data(desc=msg.text)
    await state.set_state(JobStates.contact)
    await msg.answer("☎️ Telefon:")


@router.message(JobStates.contact)
async def add_job_contact(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    job_id = db.add_job(msg.from_user.id, data['title'], data['job_type'],
                        data['region'], data['salary'], data['desc'], msg.text)

    await msg.answer("✅ Ish e'loni yuborildi!", reply_markup=job_kb())

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id,
                                   f"🆕 Yangi ish #{job_id}\n{data['title']} - {data['region']}\n"
                                   f"Tasdiqlash: /approve_job_{job_id}")
        except:
            pass


# ===== ESLATMA =====
@router.message(F.text == "📅 Eslatma")
async def rem_menu(msg: Message):
    await msg.answer("📅 Eslatmalar", reply_markup=rem_kb())


@router.message(F.text == "➕ Yangi")
async def add_rem(msg: Message, state: FSMContext):
    await state.set_state(RemStates.title)
    await msg.answer("📝 Nom:", reply_markup=ReplyKeyboardRemove())


@router.message(RemStates.title)
async def add_rem_title(msg: Message, state: FSMContext):
    await state.update_data(title=msg.text)
    await state.set_state(RemStates.rtype)
    await msg.answer(
        "📋 Turi:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Imtihon"), KeyboardButton(text="Dars")],
            [KeyboardButton(text="To'lov"), KeyboardButton(text="Boshqa")]
        ], resize_keyboard=True)
    )


@router.message(RemStates.rtype)
async def add_rem_type(msg: Message, state: FSMContext):
    await state.update_data(rtype=msg.text)
    await state.set_state(RemStates.date)
    await msg.answer("📅 Sana (DD.MM.YYYY):", reply_markup=ReplyKeyboardRemove())


@router.message(RemStates.date)
async def add_rem_date(msg: Message, state: FSMContext):
    try:
        d, m, y = msg.text.split('.')
        await state.update_data(date=f"{y}-{m}-{d}")
        await state.set_state(RemStates.time)
        await msg.answer("🕐 Vaqt (HH:MM):")
    except:
        await msg.answer("❌ Noto'g'ri! (DD.MM.YYYY)")


@router.message(RemStates.time)
async def add_rem_time(msg: Message, state: FSMContext):
    try:
        data = await state.get_data()
        await state.clear()

        remind_at = f"{data['date']} {msg.text}"
        datetime.strptime(remind_at, "%Y-%m-%d %H:%M")  # validate

        rem_id = db.add_reminder(msg.from_user.id, data['title'], data['rtype'], remind_at)
        await msg.answer("✅ Eslatma qo'shildi!", reply_markup=rem_kb())
    except:
        await msg.answer("❌ Noto'g'ri! (HH:MM)", reply_markup=rem_kb())


@router.message(F.text == "📋 Ro'yxat")
async def list_rem(msg: Message):
    rems = db.get_user_reminders(msg.from_user.id)
    if not rems:
        await msg.answer("📭 Eslatmalar yo'q")
        return

    text = f"📋 <b>Eslatmalaringiz ({len(rems)})</b>\n\n"
    for r in rems:
        text += f"📅 {r['title']}\n   {r['remind_at']} | {r['type']}\n\n"
    await msg.answer(text, parse_mode="HTML")


# ===== STATS =====
@router.message(F.text == "📊 Stats")
async def stats(msg: Message):
    apts = len([a for a in db.data["apartments"] if a["owner"] == msg.from_user.id])
    jobs = len([j for j in db.data["jobs"] if j["owner"] == msg.from_user.id])
    rems = len(db.get_user_reminders(msg.from_user.id))

    text = f"📊 <b>Statistika</b>\n\n"
    text += f"🏠 E'lonlar: {apts}\n"
    text += f"💼 Ish e'lonlari: {jobs}\n"
    text += f"📅 Eslatmalar: {rems}"
    await msg.answer(text, parse_mode="HTML")


# ===== ADMIN =====
@router.message(Command("approve_apt"))
async def approve_apt(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    try:
        apt_id = int(msg.text.split('_')[-1])
        if db.approve_apt(apt_id):
            await msg.answer(f"✅ Kvartira #{apt_id} tasdiqlandi!")
    except:
        pass


@router.message(Command("approve_job"))
async def approve_job(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    try:
        job_id = int(msg.text.split('_')[-1])
        if db.approve_job(job_id):
            await msg.answer(f"✅ Ish #{job_id} tasdiqlandi!")
    except:
        pass


@router.message(F.text == "🔙 Orqaga")
async def back(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("🏠 Bosh sahifa", reply_markup=main_kb())


# ===== SCHEDULER =====
async def check_reminders():
    rems = db.get_pending_reminders()
    for r in rems:
        try:
            await bot.send_message(r["user"], f"🔔 <b>ESLATMA!</b>\n\n{r['title']}\n\n⏰ {r['remind_at']}",
                                   parse_mode="HTML")
            db.mark_sent(r["id"])
        except Exception as e:
            logger.error(f"Reminder error: {e}")


# ===== MAIN =====
async def main():
    dp.include_router(router)
    scheduler.add_job(check_reminders, 'interval', minutes=1)
    scheduler.start()
    logger.info("🚀 TalabaLife Bot ishga tushdi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())