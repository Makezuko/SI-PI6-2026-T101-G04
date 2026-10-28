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
    segment_experience_block,
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

    def test_known_category_prefix_is_removed_and_preserved_as_metadata(self):
        details = split_skill_block_details(
            "CI Tools: Jenkins, Git\nSCM Tools: SVN\nContainers: Docker"
        )
        self.assertEqual(
            [item["skill"] for item in details],
            ["Jenkins", "Git", "SVN", "Docker"],
        )
        self.assertEqual(
            [item["category"] for item in details],
            ["CI Tools", "CI Tools", "SCM Tools", "Containers"],
        )
        self.assertEqual(details[0]["evidence_text"], "CI Tools: Jenkins, Git")

    def test_skill_details_keep_specific_source_line(self):
        result = extract_skills(
            text=(
                "TECHNICAL SKILLS\n"
                "Programming Languages: Python, Java\n"
                "EXPERIENCE\n"
                "Software Engineer"
            ),
            ner_entities=[],
        )
        python_detail = next(
            item for item in result["skill_details"] if item["skill"] == "Python"
        )
        self.assertIn("Programming Languages: Python, Java", python_detail["evidence"])
        self.assertIn("Programming Languages", python_detail["categories"])


    def test_experience_is_split_into_responsibilities(self):
        """Deve separar responsabilidades e preservar o cabeçalho."""
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
        experiences = [item for item in blocks if item["source"] == "experience"]

        self.assertEqual(len(experiences), 2)
        self.assertEqual(
            experiences[0]["text"],
            "Installed and configured Jenkins for automated builds and tests.",
        )
        self.assertEqual(
            experiences[1]["text"],
            "Implemented automatic environment creation using Chef.",
        )
        self.assertEqual(experiences[0]["evidence_type"], "responsibility")
        self.assertIn("Example Company", experiences[0]["context_header"])
        self.assertIn("Role: Build & Release", experiences[0]["context_header"])
        self.assertTrue(any("Example project" in item["text"] for item in blocks))

    def test_segmentation_stops_after_blank_before_non_bullet_text(self):
        """Não deve anexar um possível cargo seguinte à última responsabilidade."""
        block = {
            "text": (
                "Example Company\n"
                "Role: DevOps Engineer\n"
                "Responsibilities:\n"
                "• Installed and configured Jenkins.\n"
                "\n"
                "Software Engineer at Another Company\n"
                "2020–2021\n"
                "• Developed Python services."
            ),
            "source": "experience",
            "heading": "WORK EXPERIENCE",
            "start_line": 1,
            "end_line": 8,
        }
        result = segment_experience_block(block)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["text"], "Installed and configured Jenkins.")
        self.assertNotIn("Another Company", result[0]["text"])
        self.assertEqual(result[1]["text"], "Developed Python services.")
        self.assertIn("Another Company", result[1]["context_header"])

    def test_declaration_ends_experience_context(self):
        """Declaration e texto seguinte não devem virar experiência."""
        resume = """
WORK EXPERIENCE
Example Company
Role: Build & Release
Responsibilities:
• Managed deployment issues.

Declaration
I hereby declare that the statements are correct.

software engineer
Another Company

Technical Skills
Jenkins, Docker
"""
        blocks = extract_context_blocks(resume)
        experiences = [item for item in blocks if item["source"] == "experience"]

        self.assertEqual(len(experiences), 1)
        self.assertEqual(experiences[0]["text"], "Managed deployment issues.")
        all_experience_text = "\n".join(item["text"] for item in experiences)
        self.assertNotIn("Declaration", all_experience_text)
        self.assertNotIn("Another Company", all_experience_text)


if __name__ == "__main__":
    unittest.main()