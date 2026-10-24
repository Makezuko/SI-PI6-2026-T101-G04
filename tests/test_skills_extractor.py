"""
Testes do extrator híbrido de competências.
"""

import unittest

from src.nlp.skills_extractor import (
    extract_skills,
    find_skill_sections,
    split_skill_block,
    split_skill_block_details,
    is_valid_skill_candidate,
    extract_context_blocks,
)


class SkillsExtractorTests(unittest.TestCase):

    def test_explicit_skills_section(self):
        """Deve extrair Skills e parar em Experience."""
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
        """Deve reconhecer título e conteúdo na mesma linha."""
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
        """Deve remover prefixos internos da seção."""
        block = """
Programming Languages: Python, Java
Databases: PostgreSQL, MySQL
Tools: Git, Docker
"""

        skills = split_skill_block(block)

        self.assertIn("Python", skills)
        self.assertIn("Java", skills)
        self.assertIn("PostgreSQL", skills)
        self.assertIn("MySQL", skills)
        self.assertIn("Git", skills)
        self.assertIn("Docker", skills)

    def test_combines_section_and_ner(self):
        """Deve unir fontes e remover competências duplicadas."""
        resume = """
SKILLS
Python, FastAPI
"""

        ner_entities = [
            {
                "label": "SKILLS",
                "text": "Python, PostgreSQL",
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
            for item in result["skill_details"]
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
        """Deve reconhecer marcadores com problema de codificação."""
        block = "Python â€¢ React â€¢ SQL"

        skills = split_skill_block(block)

        self.assertEqual(
            skills,
            [
                "Python",
                "React",
                "SQL",
            ],
        )

    def test_no_skills_section(self):
        """Sem seção de Skills e sem NER, deve retornar lista vazia."""
        resume = """
John Smith
Professional Experience
Software Engineer at Example Company
Education
Bachelor of Science
"""

        sections = find_skill_sections(resume)

        result = extract_skills(
            text=resume,
            ner_entities=[],
        )

        self.assertEqual(sections, [])
        self.assertEqual(result["skills"], [])

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

    def test_known_category_prefix_is_removed_and_preserved(self):
        """Deve separar a categoria da habilidade e preservar a linha original."""
        details = split_skill_block_details(
            "CI Tools: Jenkins, Git\n"
            "SCM Tools: SVN\n"
            "Containers: Docker"
        )

        self.assertEqual(
            [item["skill"] for item in details],
            [
                "Jenkins",
                "Git",
                "SVN",
                "Docker",
            ],
        )

        self.assertEqual(
            [item["category"] for item in details],
            [
                "CI Tools",
                "CI Tools",
                "SCM Tools",
                "Containers",
            ],
        )

        self.assertEqual(
            details[0]["evidence_text"],
            "CI Tools: Jenkins, Git",
        )

    def test_skill_details_keep_specific_source_line(self):
        """Deve preservar a linha original e a categoria de cada habilidade."""
        resume = (
            "TECHNICAL SKILLS\n"
            "Programming Languages: Python, Java\n"
            "EXPERIENCE\n"
            "Software Engineer"
        )

        result = extract_skills(
            text=resume,
            ner_entities=[],
        )

        python_detail = next(
            item
            for item in result["skill_details"]
            if item["skill"] == "Python"
        )

        self.assertIn(
            "Programming Languages: Python, Java",
            python_detail["evidence"],
        )

        self.assertIn(
            "Programming Languages",
            python_detail["categories"],
        )

    def test_experience_is_split_into_responsibilities(self):
        """Deve separar responsabilidades e preservar o cabeçalho da experiência."""
        resume = """
EXPERIENCE
Example Company
Role: Build & Release
Environment: Jenkins, Chef
Responsibilities:
• Installed and configured Jenkins for automated builds and tests.
• Implemented automatic environment creation using Chef.
PROJECTS
Example project
"""

        blocks = extract_context_blocks(resume)

        # Filtra os blocos de experiência, sem contar a seção de projetos.
        experience_blocks = [
            block
            for block in blocks
            if block["source"] == "experience"
        ]

        self.assertEqual(
            len(experience_blocks),
            2,
            msg=f"Blocos de experiência encontrados: {experience_blocks}",
        )

        self.assertEqual(
            experience_blocks[0]["text"],
            "Installed and configured Jenkins for automated builds and tests.",
        )

        self.assertEqual(
            experience_blocks[1]["text"],
            "Implemented automatic environment creation using Chef.",
        )

        self.assertEqual(
            experience_blocks[0]["evidence_type"],
            "responsibility",
        )

        self.assertIn(
            "Example Company",
            experience_blocks[0]["context_header"],
        )

        self.assertIn(
            "Role: Build & Release",
            experience_blocks[0]["context_header"],
        )

        # A seção de projetos deve continuar preservada.
        self.assertTrue(
            any(
                "Example project" in block["text"]
                for block in blocks
            ),
            msg=f"Bloco de projeto não encontrado: {blocks}",
        )


if __name__ == "__main__":
    unittest.main()