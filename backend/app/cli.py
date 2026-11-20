"""
CLI management commands.

Usage:
    python -m app.cli create-admin
"""
from __future__ import annotations

import asyncio
import sys

import bcrypt
import click
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import settings
from .models.admin import AdminUser


@click.group()
def cli() -> None:
    pass


@cli.command("create-admin")
@click.option("--email", prompt="Email", help="Admin email address")
@click.option(
    "--password",
    prompt="Password",
    hide_input=True,
    confirmation_prompt=True,
    help="Admin password",
)
def create_admin(email: str, password: str) -> None:
    """Create the admin user. Run once after initial deployment."""
    asyncio.run(_create_admin(email, password))


async def _create_admin(email: str, password: str) -> None:
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        result = await db.execute(select(AdminUser).where(AdminUser.email == email))
        if result.scalar_one_or_none() is not None:
            click.echo(f"Error: admin account '{email}' already exists.", err=True)
            await engine.dispose()
            sys.exit(1)

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = AdminUser(email=email, password_hash=password_hash)
        db.add(user)
        await db.commit()
        click.echo(f"Admin account '{email}' created.")

    await engine.dispose()


if __name__ == "__main__":
    cli()
