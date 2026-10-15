from __future__ import annotations

import unittest

from pixelle_agent.renderer import fill_template


class TemplateRenderingTests(unittest.TestCase):
    def test_escapes_text_and_preserves_safe_line_breaks(self) -> None:
        result = fill_template(
            "<div>{{text}}</div>",
            {"text": "<script>alert('x')</script> & facts\nsecond line"},
        )
        self.assertEqual(
            result,
            "<div>&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; &amp; facts<br>second line</div>",
        )

    def test_substitutes_default_and_known_values(self) -> None:
        result = fill_template(
            "<b>{{title}}</b><i>{{author=@Pixelle.AI}}</i>",
            {"title": "Hello", "author": "Arena Agent"},
        )
        self.assertEqual(result, "<b>Hello</b><i>Arena Agent</i>")

    def test_color_parameter_accepts_hex_and_rejects_css_injection(self) -> None:
        self.assertEqual(
            fill_template("color:{{accent:color=#fff}}", {"accent": "#12ab34"}),
            "color:#12ab34",
        )
        with self.assertRaisesRegex(ValueError, "hex color"):
            fill_template("color:{{accent:color=#fff}}", {"accent": "red; background:url(x)"})

    def test_numeric_parameter_rejects_non_finite_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            fill_template("font-size:{{size:number=32}}", {"size": float("inf")})

    def test_unprovided_parameters_use_defaults_or_empty_text(self) -> None:
        result = fill_template("{{unknown}} {{label:bool=true}}", {})
        self.assertEqual(result, " true")


if __name__ == "__main__":
    unittest.main()
