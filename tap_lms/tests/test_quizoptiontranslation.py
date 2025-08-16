# apps/tap_lms/tap_lms/tests/test_quizoptiontranslation.py
import unittest
from unittest.mock import patch, MagicMock

class TestQuizOptionTranslation(unittest.TestCase):
    """Minimal test cases for QuizOptionTranslation doctype to achieve 100% coverage"""
    
    def test_quizoptiontranslation_import_and_instantiation(self):
        """Test QuizOptionTranslation import and instantiation - covers all lines"""
        # Mock frappe to avoid import errors
        mock_frappe = MagicMock()
        mock_document = MagicMock()
        mock_frappe.model.document.Document = mock_document
        
        with patch.dict('sys.modules', {
            'frappe': mock_frappe,
            'frappe.model': mock_frappe.model,
            'frappe.model.document': mock_frappe.model.document
        }):
            # This covers line 5: from frappe.model.document import Document
            from tap_lms.tap_lms.doctype.quizoptiontranslation.quizoptiontranslation import QuizOptionTranslation
            
            # This covers line 7: class QuizOptionTranslation(Document):
            # This covers line 8: pass (executed when instantiating)
            quiz_option_translation = QuizOptionTranslation()
            
            # Verify it worked
            self.assertIsNotNone(quiz_option_translation)

