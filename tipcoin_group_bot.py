import os
import re
import json
from dotenv import load_dotenv
from telegram import Update, ChatMember
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters,  ChatMemberHandler
from web3 import Web3
from config import TELEGRAM_TOKEN

# ===========================
# CONFIGURACIÓN
# ===========================


# RPC de BSC Testnet
BSC_TESTNET_RPC = "https://data-seed-prebsc-1-s1.binance.org:8545/"
web3 = Web3(Web3.HTTPProvider(BSC_TESTNET_RPC))

# Dirección del contrato de TipCoin en Testnet
CONTRACT_ADDRESS = "0x71f33080c2d0b562A55BCF04675d2F3Fa7bead59"

# ABI genérico ERC-20
ERC20_ABI = '''
[
    {"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},
    {"constant":true,"inputs":[{"name":"owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"}
]
'''

# Cargar contrato de TipCoin
contract = web3.eth.contract(address=web3.to_checksum_address(CONTRACT_ADDRESS), abi=json.loads(ERC20_ABI))

# Base de datos en memoria
group_wallets = {}   # {group_id: wallet_address}
user_wallets = {}    # {user_id: wallet_address}
bot_activo = True    # Estado del bot (True = activo, False = suspendido)

# ===========================
# FUNCIONES
# ===========================
def is_valid_wallet(address: str) -> bool:
    return bool(re.match(r"^0x[a-fA-F0-9]{40}$", address))

def get_token_balance(wallet):
    try:
        decimals = contract.functions.decimals().call()
        balance = contract.functions.balanceOf(web3.to_checksum_address(wallet)).call()
        return balance / (10 ** decimals)
    except:
        return None
async def send_help_on_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member and update.my_chat_member.new_chat_member.user.id == context.bot.id:
        chat_id = update.effective_chat.id
        help_text = (
            "👋 ¡Hola! Soy el bot de TipCoin.\n\n"
             "Soy tu bot de donaciones y propinas favorito. Usame para donar al grupo o usuario que quieras"
            "💡 *Comandos disponibles:*\n"
            "tip @wallet <direccion> - Guarda tu wallet personal\n"
            "tip @adminwallet <direccion> - *Solo admins*: Guarda la wallet del grupo\n"
            "tip @tip <cantidad> - Donación al dueño del grupo\n"
            "tip @donate <usuario> <cantidad> - Donación a un usuario\n"
            "tip @balance - Muestra tu saldo en TIP\n"
            "tip @cancel - *Solo admins*: Suspende el bot\n"
            "tip @start - *Solo admins*: Reactiva el bot\n"
            "tip @help - Muestra esta ayuda\n\n"
            "🪙 *Para usar el bot necesitas TipCoin.*\n"
            f"📄 *Contrato:* `{CONTRACT_ADDRESS}`\n"
            "_Todas las propinas se firman con tu propia wallet_"
        )
        await context.bot.send_message(chat_id=chat_id, text=help_text, parse_mode="Markdown")
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id != context.bot.id:  # No saludar al bot
            help_text = (
                f"👋 ¡Bienvenido {member.first_name}!\n\n"
                "Soy tu bot de donaciones y propinas favorito. Usame para donar al grupo o usuario que quieras"
                "💡 *Comandos disponibles:*\n"
                "tip @wallet <direccion> - Guarda tu wallet personal\n"
                "tip @adminwallet <direccion> - *Solo admins*: Guarda la wallet del grupo\n"
                "tip @tip <cantidad> - Donación al dueño del grupo\n"
                "tip @donate <usuario> <cantidad> - Donación a un usuario\n"
                "tip @balance - Muestra tu saldo en TIP\n"
                "tip @cancel - *Solo admins*: Suspende el bot\n"
                "tip @start - *Solo admins*: Reactiva el bot\n"
                "tip @help - Muestra esta ayuda\n\n"
                "🪙 *Para usar el bot necesitas TipCoin.*\n"
                f"📄 *Contrato:* `{CONTRACT_ADDRESS}`\n"
                "_Todas las propinas se firman con tu propia wallet_"
            )
            await update.message.reply_text(help_text, parse_mode="Markdown")

# ===========================
# HANDLER PRINCIPAL DE COMANDOS
# ===========================
async def handle_tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_activo

    text = update.message.text.strip()

    # Verificar que empieza por "tip "
    if not text.lower().startswith("tip "):
        return

    args = text.split()
    if len(args) < 2:
        await update.message.reply_text("❌ Uso: tip @comando ...")
        return

    comando = args[1].lower()
    params = args[2:]

    # Si el bot está suspendido y no es @start → ignorar
    if not bot_activo and comando != "@start":
        await update.message.reply_text("⏸ El bot está suspendido. Solo un admin puede reactivarlo con tip @start.")
        return

    # ---------------------------
    # HELP
    # ---------------------------
    if comando == "@help":
        help_text = (
            "💡 *Comandos disponibles:*\n\n"
            "tip @wallet <direccion> - Guarda tu wallet personal\n"
            "tip @adminwallet <direccion> - *Solo admins*: Guarda la wallet del grupo\n"
            "tip @tip <cantidad> - Donación al dueño del grupo\n"
            "tip @donate <usuario> <cantidad> - Donación a un usuario\n"
            "tip @balance - Muestra tu saldo en TIP\n"
            "tip @cancel - *Solo admins*: Suspende el bot\n"
            "tip @start - *Solo admins*: Reactiva el bot\n"
            "tip @help - Muestra esta ayuda\n\n"
            "🪙 *Para usar el bot necesitas TipCoin.*\n"
            f"📄 *Contrato:* `{CONTRACT_ADDRESS}`\n"
            "_Todas las propinas se firman con tu propia wallet_"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")

    # ---------------------------
    # WALLET PERSONAL
    # ---------------------------
    elif comando == "@wallet":
        if not params:
            await update.message.reply_text("❌ Debes poner una dirección: tip @wallet 0xTU_DIRECCION")
            return

        address = params[0]
        if not is_valid_wallet(address):
            await update.message.reply_text("❌ Dirección inválida. Debe empezar por 0x y tener 42 caracteres.")
            return

        user_wallets[update.effective_user.id] = address
        await update.message.reply_text(f"✅ Wallet personal guardada: {address}")

    # ---------------------------
    # WALLET DEL GRUPO (solo admin)
    # ---------------------------
    elif comando == "@adminwallet":
        if not params:
            await update.message.reply_text("❌ Debes poner una dirección: tip @adminwallet 0xDIRECCION")
            return

        address = params[0]
        if not is_valid_wallet(address):
            await update.message.reply_text("❌ Dirección inválida. Debe empezar por 0x y tener 42 caracteres.")
            return

        chat = update.effective_chat
        user = update.effective_user

        if chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("❌ Este comando solo se puede usar en grupos.")
            return

        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in [ChatMember.OWNER, ChatMember.ADMINISTRATOR]:
            await update.message.reply_text("❌ Solo un administrador puede configurar la wallet del grupo.")
            return

        group_wallets[chat.id] = address
        await update.message.reply_text(f"✅ Wallet del grupo guardada por admin: {address}")

    # ---------------------------
    # BALANCE
    # ---------------------------
    elif comando == "@balance":
        user_id = update.effective_user.id
        if user_id not in user_wallets:
            await update.message.reply_text("❌ No tienes wallet registrada. Usa tip @wallet para añadirla.")
            return
        wallet = user_wallets[user_id]
        balance = get_token_balance(wallet)
        if balance is None:
            await update.message.reply_text("❌ Error al consultar saldo.")
        else:
            await update.message.reply_text(f"💰 Tu saldo: {balance} TIP")

    # ---------------------------
    # TIP (propina)
    # ---------------------------
    elif comando == "@tip":
        if not params:
            await update.message.reply_text("❌ Uso: tip @tip cantidad")
            return
        amount = params[0]
        group_id = update.effective_chat.id
        if group_id not in group_wallets:
            await update.message.reply_text("❌ Este grupo no tiene wallet configurada por el admin.")
            return
        wallet = group_wallets[group_id]
        link = f"https://metamask.app.link/send/{wallet}@56?value={amount}"
        await update.message.reply_text(
            f"💸 Propina de {amount} TIP → {wallet}\n[Haz clic aquí para enviar]({link})",
            parse_mode="Markdown"
        )
# ---------------------------
# DONAR A USUARIO
# ---------------------------
    elif comando == "@donate":
        if len(params) < 2:
            await update.message.reply_text("❌ Uso: tip @donate <id_usuario> <cantidad>")
            return

        user_target = params[0]
        cantidad = params[1]

        wallet = None
        for uid, addr in user_wallets.items():
            if str(uid) == user_target:
                wallet = addr

        if not wallet:
            await update.message.reply_text("❌ El usuario no tiene wallet registrada.")
            return

        link = f"https://metamask.app.link/send/{wallet}@56?value={cantidad}"
        await update.message.reply_text(
            f"💸 Propina de {cantidad} TIP → {wallet}\n[Haz clic aquí para enviar]({link})",
            parse_mode="Markdown"
        )

    # ---------------------------
    # CANCELAR (suspender bot)
    # ---------------------------
    elif comando == "@cancel":
        chat = update.effective_chat
        user = update.effective_user

        if chat.type in ["group", "supergroup"]:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in [ChatMember.OWNER, ChatMember.ADMINISTRATOR]:
                await update.message.reply_text("❌ Solo un administrador puede suspender el bot.")
                return

        bot_activo = False
        await update.message.reply_text("⏸ Bot suspendido por administrador.")

    # ---------------------------
    # REACTIVAR BOT
    # ---------------------------
    elif comando == "@start":
        chat = update.effective_chat
        user = update.effective_user

        if chat.type in ["group", "supergroup"]:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in [ChatMember.OWNER, ChatMember.ADMINISTRATOR]:
                await update.message.reply_text("❌ Solo un administrador puede reactivar el bot.")
                return

        bot_activo = True
        await update.message.reply_text("▶ Bot reactivado por administrador.")

    else:
        await update.message.reply_text("❌ Comando no reconocido. Usa tip @help para ver la ayuda.")

# ===========================
# INICIAR BOT
# ===========================
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tip_command))

print("🤖 Bot de TipCoin en marcha con prefijo 'tip'...")
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
app.add_handler(ChatMemberHandler(send_help_on_join, chat_member_types=["my_chat_member"]))


app.run_polling()
