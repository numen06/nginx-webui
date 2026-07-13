import asyncio
import unittest
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database as database_module
from app.auth import require_admin
from app.models import Base, User
from app.routers.users import UserCreate, UserUpdate, create_user, delete_user, update_user


class AdminPermissionTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.last_admin = User(
            username='primary',
            password_hash='test',
            is_active=True,
            is_admin=True,
        )
        self.db.add(self.last_admin)
        self.db.commit()
        self.db.refresh(self.last_admin)
        self.operator = User(
            id=999,
            username='operator',
            password_hash='test',
            is_active=True,
            is_admin=True,
        )
        self.request = SimpleNamespace(headers={}, client=None)

    def tearDown(self):
        self.db.close()

    def test_non_admin_is_rejected(self):
        user = User(username='viewer', password_hash='test', is_active=True, is_admin=False)
        with self.assertRaises(HTTPException) as raised:
            require_admin(user)
        self.assertEqual(raised.exception.status_code, 403)

    def test_last_active_admin_cannot_be_demoted(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(update_user(
                self.last_admin.id,
                UserUpdate(is_admin=False),
                request=None,
                current_user=self.operator,
                db=self.db,
            ))
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn('唯一的超级管理员', raised.exception.detail)

    def test_admin_role_is_transferred_to_one_active_user(self):
        successor = User(
            username='successor',
            password_hash='test',
            is_active=True,
            is_admin=False,
        )
        self.db.add(successor)
        self.db.commit()
        self.db.refresh(successor)

        asyncio.run(update_user(
            successor.id,
            UserUpdate(is_admin=True),
            request=self.request,
            current_user=self.last_admin,
            db=self.db,
        ))

        self.db.refresh(self.last_admin)
        self.db.refresh(successor)
        self.assertFalse(self.last_admin.is_admin)
        self.assertTrue(successor.is_admin)
        self.assertEqual(self.db.query(User).filter(User.is_admin.is_(True)).count(), 1)

    def test_new_user_cannot_be_created_as_admin(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(create_user(
                UserCreate(username='second-admin', password='secret1', is_admin=True),
                request=self.request,
                current_user=self.last_admin,
                db=self.db,
            ))
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn('仅允许一个超级管理员', raised.exception.detail)

    def test_inactive_user_cannot_receive_admin_role(self):
        inactive = User(
            username='inactive',
            password_hash='test',
            is_active=False,
            is_admin=False,
        )
        self.db.add(inactive)
        self.db.commit()
        self.db.refresh(inactive)

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(update_user(
                inactive.id,
                UserUpdate(is_admin=True),
                request=None,
                current_user=self.last_admin,
                db=self.db,
            ))
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn('必须保持启用', raised.exception.detail)

    def test_migration_preserves_transferred_admin(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        original_admin = User(
            username='admin', password_hash='test', is_active=True, is_admin=False,
        )
        successor = User(
            username='successor', password_hash='test', is_active=True, is_admin=True,
        )
        session.add_all([original_admin, successor])
        session.commit()
        original_engine = database_module.engine
        database_module.engine = engine
        try:
            database_module._migrate_add_user_admin()
        finally:
            database_module.engine = original_engine
        session.expire_all()
        self.assertFalse(session.query(User).filter(User.username == 'admin').one().is_admin)
        self.assertTrue(session.query(User).filter(User.username == 'successor').one().is_admin)
        session.close()

    def test_migration_collapses_multiple_admins(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        session.add_all([
            User(username='admin', password_hash='test', is_active=True, is_admin=True),
            User(username='legacy-admin', password_hash='test', is_active=True, is_admin=True),
        ])
        session.commit()
        original_engine = database_module.engine
        database_module.engine = engine
        try:
            database_module._migrate_add_user_admin()
        finally:
            database_module.engine = original_engine
        session.expire_all()
        admins = session.query(User).filter(User.is_admin.is_(True)).all()
        self.assertEqual([admin.username for admin in admins], ['admin'])
        session.close()

    def test_last_active_admin_cannot_be_deleted(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(delete_user(
                self.last_admin.id,
                request=None,
                current_user=self.operator,
                db=self.db,
            ))
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn('最后一个有效的超级管理员', raised.exception.detail)

    def test_admin_cannot_delete_self(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(delete_user(
                self.last_admin.id,
                request=None,
                current_user=self.last_admin,
                db=self.db,
            ))
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn('不能删除自己的账户', raised.exception.detail)


if __name__ == '__main__':
    unittest.main()
