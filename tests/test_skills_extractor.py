"""
Testes do extrator híbrido de competências.
"""

import unittest

from src.nlp.skills_extractor import (
    extract_skills,
    find_skill_sections,
    split_skill_block,
    extract_skills,
    is_valid_skill_candidate,
)


class SkillsExtractorTests(
    unittest.TestCase
):

    def test_explicit_skills_section(self):
        """
        Deve extrair uma seção de Skills e parar em Experience.
        """
        resume = """
John Smith

TECHNICAL SKILLS
Python, FastAPI, PostgreSQL
React • Next.js • TypeScript

EXPERIENCE
Software Engineer at Example Company
"""

        result = extract_skills(
            text=resume,
            ner_entities=[],
        )

        self.assertEqual(
            result["skills"],
            [
                "Python",
                "FastAPI",
                "PostgreSQL",
                "React",
                "Next.js",
                "TypeScript",
            ],
        )

        self.assertNotIn(
            "Software Engineer at Example Company",
            result["skills"],
        )

    def test_inline_section(self):
        """
        Deve reconhecer título e conteúdo na mesma linha.
        """
        resume = """
Technical Skills: Java, Spring Boot, SQL
Education
Bachelor of Science
"""

        result = extract_skills(
            text=resume,
            ner_entities=[],
        )

        self.assertEqual(
            result["skills"],
            [
                "Java",
                "Spring Boot",
                "SQL",
            ],
        )

    def test_category_prefix(self):
        """
        Deve remover prefixos internos da seção.
        """
        block = """
Programming Languages: Python, Java
Databases: PostgreSQL, MySQL
Tools: Git, Docker
"""

        skills = split_skill_block(
            block
        )

        self.assertIn(
            "Python",
            skills,
        )

        self.assertIn(
            "Java",
            skills,
        )

        self.assertIn(
            "PostgreSQL",
            skills,
        )

        self.assertIn(
            "MySQL",
            skills,
        )

        self.assertIn(
            "Git",
            skills,
        )

        self.assertIn(
            "Docker",
            skills,
        )

    def test_combines_section_and_ner(self):
        """
        Deve unir as fontes e remover competências duplicadas.
        """
        resume = """
SKILLS
Python, FastAPI
"""

        ner_entities = [
            {
                "label": "SKILLS",
                "text": (
                    "Python, PostgreSQL"
                ),
                "confidence": 0.85,
                "start": 8,
                "end": 26,
            }
        ]

        result = extract_skills(
            text=resume,
            ner_entities=ner_entities,
        )

        self.assertEqual(
            result["skills"],
            [
                "Python",
                "FastAPI",
                "PostgreSQL",
            ],
        )

        python_details = next(
            item
            for item
            in result["skill_details"]
            if item["skill"] == "Python"
        )

        self.assertIn(
            "section",
            python_details["sources"],
        )

        self.assertIn(
            "ner",
            python_details["sources"],
        )

    def test_repairs_broken_bullet(self):
        """
        Deve reconhecer marcadores com problema de codificação.
        """
        block = (
            "Python â€¢ React â€¢ SQL"
        )

        skills = split_skill_block(
            block
        )

        self.assertEqual(
            skills,
            [
                "Python",
                "React",
                "SQL",
            ],
        )

    def test_no_skills_section(self):
        """
        Um currículo sem seção e sem NER deve retornar lista vazia.
        """
        resume = """
John Smith
Professional Experience
Software Engineer at Example Company
Education
Bachelor of Science
"""

        sections = find_skill_sections(
            resume
        )

        result = extract_skills(
            text=resume,
            ner_entities=[],
        )

        self.assertEqual(
            sections,
            [],
        )

        self.assertEqual(
            result["skills"],
            [],
        )

def test_rejects_invalid_ner_fragments(self):
    """Deve rejeitar fragmentos incorretos produzidos pelo NER."""
    self.assertFalse(is_valid_skill_candidate("."))
    self.assertFalse(is_valid_skill_candidate("s"))
    self.assertFalse(is_valid_skill_candidate("LS"))


def test_accepts_valid_short_skills(self):
    """Deve preservar tecnologias válidas com nomes curtos."""
    self.assertTrue(is_valid_skill_candidate("C"))
    self.assertTrue(is_valid_skill_candidate("R"))
    self.assertTrue(is_valid_skill_candidate("Go"))
    self.assertTrue(is_valid_skill_candidate("C#"))
    self.assertTrue(is_valid_skill_candidate("C++"))


if __name__ == "__main__":
    unittest.main()