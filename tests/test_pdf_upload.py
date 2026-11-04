import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from src.data.clean import anonymize_resume_text, extract_pdf_text, parse_resume_pdf


def make_sample_pdf(lines: list[str]) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=600)

    font_dict = DictionaryObject()
    font_dict[NameObject("/Type")] = NameObject("/Font")
    font_dict[NameObject("/Subtype")] = NameObject("/Type1")
    font_dict[NameObject("/BaseFont")] = NameObject("/Helvetica")
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = font_dict
    resources = DictionaryObject()
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources

    text_commands = ["BT", "/F1 12 Tf", "20 560 Td", "14 TL"]
    for i, line in enumerate(lines):
        escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        if i == 0:
            text_commands.append(f"({escaped}) Tj")
        else:
            text_commands.append(f"T* ({escaped}) Tj")
    text_commands.append("ET")

    stream = DecodedStreamObject()
    stream.set_data("\n".join(text_commands).encode("latin-1", errors="replace"))
    page[NameObject("/Contents")] = stream

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class PdfExtractionTests(unittest.TestCase):
    def test_extract_pdf_text_from_bytes(self):
        pdf_bytes = make_sample_pdf(["Carlos Silva", "Engenheiro de Software"])
        extracted = extract_pdf_text(pdf_bytes)
        self.assertIn("Carlos Silva", extracted)

    def test_parse_resume_pdf_structure(self):
        lines = [
            "Ana Ferreira",
            "ana@example.com - (11) 98765-4321",
            "TECHNICAL SKILLS",
            "Python, FastAPI, SQL, Docker",
            "EXPERIENCE",
            "Engenheira de Software",
            "Desenvolvimento de microsservicos.",
            "EDUCATION",
            "Bacharelado em Ciencia da Computacao",
        ]
        pdf_bytes = make_sample_pdf(lines)
        parsed = parse_resume_pdf(pdf_bytes, filename="ana_ferreira_cv.pdf")

        self.assertEqual(parsed["filename"], "ana_ferreira_cv.pdf")
        self.assertEqual(parsed["email"], "ana@example.com")
        self.assertIn("Python", parsed["skills"])
        self.assertIn("FastAPI", parsed["skills"])
        self.assertIn("Docker", parsed["skills"])
        self.assertTrue(len(parsed["experience_blocks"]) >= 1)
        self.assertTrue(len(parsed["education_blocks"]) >= 1)
        self.assertTrue(len(parsed["semantic_inputs"]) >= 1)
        self.assertIn("[E-MAIL OCULTO]", parsed["anonymized_text"])

    def test_anonymize_resume_text(self):
        text = "Ana Ferreira\nana@example.com\n(11) 98765-4321\n123.456.789-00\nlinkedin.com/in/anaferreira"
        anonymized = anonymize_resume_text(text, candidate_name="Ana Ferreira")
        self.assertNotIn("ana@example.com", anonymized)
        self.assertNotIn("(11) 98765-4321", anonymized)
        self.assertNotIn("123.456.789-00", anonymized)
        self.assertNotIn("Ana Ferreira", anonymized)
        self.assertIn("[E-MAIL OCULTO]", anonymized)
        self.assertIn("[TELEFONE OCULTO]", anonymized)
        self.assertIn("[CPF OCULTO]", anonymized)
        self.assertIn("[NOME OCULTO]", anonymized)

    def test_invalid_pdf_raises_value_error(self):
        with self.assertRaises((ValueError, Exception)):
            extract_pdf_text(b"not a valid pdf content")


if __name__ == "__main__":
    unittest.main()
