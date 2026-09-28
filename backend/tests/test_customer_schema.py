import unittest

from app.schemas.customer import CustomerCreate, CustomerUpdate


class CustomerBankSchemaTest(unittest.TestCase):
    def test_create_accepts_bank_fields(self):
        payload = CustomerCreate(customer_code="C-1", name="客户", bank_name="银行", bank_account="123")
        self.assertEqual(payload.bank_name, "银行")
        self.assertEqual(payload.bank_account, "123")

    def test_update_accepts_bank_fields(self):
        payload = CustomerUpdate(bank_name="银行", bank_account="123")
        self.assertEqual(payload.bank_name, "银行")
        self.assertEqual(payload.bank_account, "123")


if __name__ == "__main__":
    unittest.main()
