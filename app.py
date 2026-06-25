#!/usr/bin/env python
import asyncio
import asyncpg
import logging
from dotenv import load_dotenv
from config import NOTIFICATION_DAYS, DB_CONFIG

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def get_conn():
    return await asyncpg.connect(**DB_CONFIG)

async def check_subscriptions():
    conn = await get_conn()
    print('conn >>>', conn)
    try:
        for days in NOTIFICATION_DAYS:
            rows = await conn.fetch("""
                SELECT
                    u.telegram_user_id,
                    u.email,
                    vc.payment_id,
                    MIN(vc.wg_easy_name) AS wg_easy_name,
                    p.number_orders_count,
                    MIN(vc.session_end) AS expires_at
                FROM users u
                JOIN payments p ON p.user_id = u.id
                JOIN vpn_configs vc ON vc.payment_id = p.payment_id
                WHERE vc.session_end >= (CURRENT_DATE + $1::int)::timestamp
                    AND vc.session_end <  (CURRENT_DATE + ($1::int + 1))::timestamp
                    AND NOT EXISTS (
                        SELECT 1 FROM notifications_queue nq
                        WHERE nq.payment_id = vc.payment_id
                        AND nq.sent = FALSE
                    )
                GROUP BY u.telegram_user_id, u.email, vc.payment_id, p.number_orders_count
            """, days)
            if rows:
                await conn.executemany("""
                    INSERT INTO notifications_queue
                    (telegram_user_id, email, payment_id, wg_easy_name, number_orders_count, expires_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, [
                    (row['telegram_user_id'], row['email'],
                     row['payment_id'], row['wg_easy_name'], row['number_orders_count'], row['expires_at'])
                    for row in rows
                ])
                logger.info(f"Added {len(rows)} notifications for {days} day(s)")
            else:
                logger.info(f"No new notifications for {days} day(s)")
    finally:
        await conn.close()

async def main():
    logger.info("Config Checker started")
    while True:
        try:
            await check_subscriptions()
            await asyncio.sleep(86400)
        except Exception as e:
            logger.error(f"Error: {e}")
            await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
