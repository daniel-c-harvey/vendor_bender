import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from invoice_importer.storage.tables import Base

async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

asyncio.run(main())