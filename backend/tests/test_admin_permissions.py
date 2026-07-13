import asyncio
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import require_admin
from app.models import Base, User
from app.routers.users import UserUpdate, delete_user, update_user


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
        self.assertIn('至少一个有效的超级管理员', raised.exception.detail)

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
