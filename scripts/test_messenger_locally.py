"""
CLI interactive test runner for Messenger Agent conversations.

Allows developers and store owners to chat naturally with the bot locally
in Jordanian Arabic without requiring live Facebook webhook delivery.

Run:
    python scripts/test_messenger_locally.py
"""

import asyncio
import sys
from pathlib import Path

# Force UTF-8 on Windows terminal
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.ai.gemini_provider import GeminiProvider
from app.config import get_settings
from app.db.client import get_supabase_client
from app.db.repositories.conversations import ConversationRepository
from app.db.repositories.customers import CustomerRepository
from app.db.repositories.faqs import FAQRepository
from app.db.repositories.orders import OrderRepository
from app.db.repositories.products import ProductRepository
from app.db.repositories.settings import StoreSettingRepository
from app.services.conversation_service import ConversationService
from app.services.order_service import OrderService


async def run_interactive_chat():
    settings = get_settings()
    store_id = settings.default_store_id
    supabase = get_supabase_client()

    print("\n=======================================================")
    print("🌹 محاكي ماسنجر الذكي — متجر هدايا الحج والعمرة")
    print("اكتب رسالتك باللهجة الأردنية واضغط Enter.")
    print("أمثلة للتجربة:")
    print("  - مرحبا، بدي هدايا لأهلي راجعين من العمرة")
    print("  - كم سعر سجادة الصلاة؟")
    print("  - بدي مسبحة ومصحف")
    print("  - بدي اطلب مسبحة لاسم احمد تلفون 0791234567 عمان طبربور")
    print("  - اكتب 'خروج' أو 'exit' للخروج.")
    print("=======================================================\n")

    # Wire dependencies
    product_repo = ProductRepository(supabase)
    order_repo = OrderRepository(supabase)
    conv_repo = ConversationRepository(supabase)
    customer_repo = CustomerRepository(supabase)
    faq_repo = FAQRepository(supabase)
    setting_repo = StoreSettingRepository(supabase)

    order_service = OrderService(
        order_repo=order_repo,
        product_repo=product_repo,
        setting_repo=setting_repo,
        conversation_repo=conv_repo,
        customer_repo=customer_repo,
    )

    ai_provider = GeminiProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
    )

    conv_service = ConversationService(
        conversation_repo=conv_repo,
        customer_repo=customer_repo,
        product_repo=product_repo,
        faq_repo=faq_repo,
        setting_repo=setting_repo,
        order_service=order_service,
        ai_provider=ai_provider,
    )

    test_psid = "local_test_user_001"

    while True:
        try:
            user_input = input("👤 أنت: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "خروج"):
                print("مع السلامة! نورتنا 🌹")
                break

            print("\n⏳ جاري المعالجة والتفكير...")
            replies = await conv_service.handle_customer_message(
                store_id=store_id,
                messenger_psid=test_psid,
                user_text=user_input,
                customer_name_hint="مستخدم تجريبي",
            )

            print("\n🤖 البوت:")
            for r in replies:
                print(r)
                print("-------------------------------------------------------")
            print()

        except KeyboardInterrupt:
            print("\nتم إنهاء المحادثة.")
            break
        except Exception as e:
            print(f"\n❌ خطأ: {e}\n")


if __name__ == "__main__":
    asyncio.run(run_interactive_chat())
