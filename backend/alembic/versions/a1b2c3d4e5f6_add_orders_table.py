"""add orders table

Revision ID: a1b2c3d4e5f6
Revises: 6fc173876332
Create Date: 2026-11-20 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '6fc173876332'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres sequence for race-safe order numbers (CBC-1001, CBC-1002, …)
    op.execute("CREATE SEQUENCE IF NOT EXISTS order_number_seq START WITH 1001")

    # Drop the stub table from the previous sprint
    op.drop_index('ix_order_items_product_id', table_name='order_items')
    op.drop_index('ix_order_items_order_id', table_name='order_items')
    op.drop_table('order_items')

    op.create_table(
        'orders',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('order_number', sa.String(), nullable=False),
        sa.Column('customer_name', sa.String(), nullable=False),
        sa.Column('customer_email', sa.String(), nullable=False),
        sa.Column('customer_phone', sa.String(), nullable=True),
        sa.Column(
            'source',
            sa.Enum('website', 'instagram', 'facebook', 'other', name='order_source'),
            nullable=False,
            server_default='website',
        ),
        sa.Column(
            'fulfillment_method',
            sa.Enum('ship', 'pickup', 'dropoff', name='fulfillment_method'),
            nullable=False,
        ),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('subtotal_cents', sa.Integer(), nullable=False),
        sa.Column('fulfillment_fee_cents', sa.Integer(), nullable=False),
        sa.Column('total_cents', sa.Integer(), nullable=False),
        sa.Column(
            'payment_status',
            sa.Enum('unpaid', 'paid', name='payment_status'),
            nullable=False,
            server_default='unpaid',
        ),
        sa.Column(
            'payment_method',
            sa.Enum('venmo', 'zelle', 'paypal', 'cash', 'other', name='payment_method'),
            nullable=True,
        ),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'fulfillment_status',
            sa.Enum(
                'received', 'in_progress', 'shipped',
                'ready_for_pickup', 'out_for_dropoff', 'delivered',
                name='fulfillment_status',
            ),
            nullable=False,
            server_default='received',
        ),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_orders_order_number'), 'orders', ['order_number'], unique=True)

    op.create_table(
        'order_items',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('order_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('variant_id', sa.Uuid(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price_cents', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_items_product_id'), 'order_items', ['product_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_order_items_product_id'), table_name='order_items')
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_table('order_items')
    op.drop_index(op.f('ix_orders_order_number'), table_name='orders')
    op.drop_table('orders')

    # Recreate the stub so a previous revision can still downgrade cleanly
    op.create_table(
        'order_items',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('order_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_order_items_order_id', 'order_items', ['order_id'], unique=False)
    op.create_index('ix_order_items_product_id', 'order_items', ['product_id'], unique=False)

    op.execute("DROP SEQUENCE IF EXISTS order_number_seq")

    sa.Enum(name='order_source').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='fulfillment_method').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='payment_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='payment_method').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='fulfillment_status').drop(op.get_bind(), checkfirst=True)
