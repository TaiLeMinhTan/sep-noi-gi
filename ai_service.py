import base64
import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from services.settings_service import (
    get_ai_config,
    get_openai_api_key,
)


LESSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "sentence": {
            "type": "string"
        },
        "context": {
            "type": "string"
        },
        "visual": {
            "type": "string"
        },
        "visual_spec": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "entities": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 6,
                    "items": {
                        "type": "string"
                    }
                },
                "action": {
                    "type": "string"
                },
                "environment": {
                    "type": "string"
                },
                "must_show": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 7,
                    "items": {
                        "type": "string"
                    }
                },
                "must_not_show": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 7,
                    "items": {
                        "type": "string"
                    }
                },
                "camera": {
                    "type": "string"
                },
            },
            "required": [
                "entities",
                "action",
                "environment",
                "must_show",
                "must_not_show",
                "camera",
            ],
        },
        "image_prompt": {
            "type": "string"
        },
        "pronunciation": {
            "type": "string"
        },
        "highlights": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "string"
            },
        },
        "patterns": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pattern": {
                        "type": "string"
                    },
                    "examples": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 3,
                        "items": {
                            "type": "string"
                        },
                    },
                },
                "required": [
                    "pattern",
                    "examples",
                ],
            },
        },
        "uses": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "string"
            },
        },
        "quiz": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {
                "type": "string"
            },
        },
        "answer": {
            "type": "integer",
            "minimum": 0,
            "maximum": 1,
        },
        "turn_prompt": {
            "type": "string"
        },
        "turn_answer": {
            "type": "string"
        },
    },
    "required": [
        "sentence",
        "context",
        "visual",
        "visual_spec",
        "image_prompt",
        "pronunciation",
        "highlights",
        "patterns",
        "uses",
        "quiz",
        "answer",
        "turn_prompt",
        "turn_answer",
    ],
}


VISUAL_CHECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
        },
        "entities_match": {
            "type": "boolean"
        },
        "action_match": {
            "type": "boolean"
        },
        "context_match": {
            "type": "boolean"
        },
        "no_conflicting_details": {
            "type": "boolean"
        },
        "instant_understanding": {
            "type": "boolean"
        },
        "missing": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "string"
            },
        },
        "conflicts": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "string"
            },
        },
        "regeneration_instruction": {
            "type": "string"
        },
    },
    "required": [
        "score",
        "entities_match",
        "action_match",
        "context_match",
        "no_conflicting_details",
        "instant_understanding",
        "missing",
        "conflicts",
        "regeneration_instruction",
    ],
}


INSTRUCTIONS = """
You create compact English micro-lessons for a visual-first
language learning app called 'Sếp Nói Gì?'.

The learner should learn less but learn deeply.

Hard rules:

- Keep the learner's sentence in English.
- Lightly correct obvious grammar only when necessary while preserving intent.
- Never translate into Vietnamese or another language.
- Teach meaning through one concrete visual scene, reusable patterns,
  collocations, and examples.
- Select only 1-3 high-value chunks/patterns.
- Prefer natural collocations over isolated vocabulary.
- Examples must fit the learner's work/life context when profile
  context is provided.
- Keep text concise enough for a phone screen.
- The picture must communicate the exact sentence without labels
  or translation.
- visual_spec is a strict scene contract.
- Capture every concrete entity, relation/action, environment,
  and critical constraint needed to make the image faithful.
- must_show contains details whose absence would make the sentence
  ambiguous or wrong.
- must_not_show prohibits plausible visual mistakes that would change meaning.
- image_prompt must faithfully implement visual_spec.
- Use one clear scene.
- No labels.
- No visible text.
- No logos.
- No watermark.
- No decorative clutter.
- Prefer literal depiction when the sentence is literal.
- For abstract workplace phrases, depict the concrete situation
  that naturally expresses the phrase.
- Do not invent unrelated actions.
- pronunciation is a short learner-friendly pronunciation cue
  for the full sentence.
- Focus pronunciation on rhythm/stress.
- No translation.
- highlights must be exact substrings in the final sentence.
- patterns should be reusable forms.
- Every pattern has exactly 3 short examples.
- uses contains exactly 3 natural sentences using the same patterns
  in nearby contexts.
- quiz contains exactly 2 options.
- One option is natural.
- One option is clearly less natural/incorrect.
- answer is zero-based index of the natural option.
- turn_prompt creates one small new situation for the learner
  to produce language.
- turn_answer is one concise model answer.
- Do not mention that you are an AI.
- Do not add prose outside the schema.
"""


VISUAL_CHECK_INSTRUCTIONS = """
You are a strict visual-semantic QA checker for an English learning app.

Judge whether the image conveys the exact sentence and scene contract
without translation.

Do not reward artistic beauty.
Score semantic fidelity only.

A high score requires:

- all required entities present
- exact action/relation visible
- correct environment/context
- no conflicting details
- learner can infer the sentence meaning quickly

Treat 98-100 as exceptional near-exact fidelity.

If anything material is missing or conflicting,
score below 98.

Return only the requested structured result.
"""


class AIServiceError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(
        get_openai_api_key()
    )


def model_name() -> str:
    return str(
        get_ai_config()[
            "openai_model"
        ]
    )


def image_model_name() -> str:
    return str(
        get_ai_config()[
            "openai_image_model"
        ]
    )


def vision_model_name() -> str:
    return str(
        get_ai_config()[
            "openai_vision_model"
        ]
    )


def visual_threshold() -> int:
    return int(
        get_ai_config()[
            "visual_match_threshold"
        ]
    )


def visual_max_attempts() -> int:
    return int(
        get_ai_config()[
            "visual_max_attempts"
        ]
    )


def visual_total_max_attempts() -> int:
    return int(
        get_ai_config()[
            "visual_total_max_attempts"
        ]
    )


def image_quality() -> str:
    return str(
        get_ai_config()[
            "openai_image_quality"
        ]
    )


def image_size() -> str:
    return str(
        get_ai_config()[
            "openai_image_size"
        ]
    )


def image_compression() -> int:
    return int(
        get_ai_config()[
            "openai_image_compression"
        ]
    )


def _client(
    api_key: str | None = None,
) -> OpenAI:

    key = (
        api_key
        or get_openai_api_key()
        or ""
    ).strip()

    if not key:
        raise AIServiceError(
            "OpenAI API key chưa được cấu hình. "
            "Vào Admin → AI Configuration."
        )

    return OpenAI(
        api_key=key
    )


def generate_lesson(
    sentence: str,
    profile: dict[str, Any],
    context_key: str,
):
    client = _client()

    profile_payload = {
        "age":
            profile.get("age"),

        "occupation":
            profile.get("occupation")
            or "",

        "industry":
            profile.get("industry")
            or "",

        "english_level":
            profile.get("english_level")
            or "",

        "goals":
            profile.get("goals")
            or "",

        "situations":
            profile.get("situations")
            or "",

        "context_key":
            context_key,
    }

    user_input = (
        "Create one micro-lesson for this sentence.\n"
        f"Sentence: {sentence}\n"
        "Learner profile: "
        + json.dumps(
            profile_payload,
            ensure_ascii=False,
        )
    )

    try:

        response = client.responses.create(
            model=model_name(),

            instructions=INSTRUCTIONS,

            input=user_input,

            store=False,

            text={
                "format": {
                    "type": "json_schema",

                    "name":
                        "sep_noigi_micro_lesson",

                    "description":
                        "A compact visual-first "
                        "English micro-lesson.",

                    "schema":
                        LESSON_SCHEMA,

                    "strict":
                        True,
                }
            },
        )

        if not response.output_text:
            raise AIServiceError(
                "OpenAI không trả về nội dung lesson."
            )

        lesson = json.loads(
            response.output_text
        )

        usage = getattr(
            response,
            "usage",
            None,
        )

        details = (
            getattr(
                usage,
                "input_tokens_details",
                None,
            )
            if usage
            else None
        )

        usage_data = {
            "input_tokens":
                getattr(
                    usage,
                    "input_tokens",
                    None,
                )
                if usage
                else None,

            "cached_input_tokens":
                getattr(
                    details,
                    "cached_tokens",
                    0,
                )
                if details
                else 0,

            "output_tokens":
                getattr(
                    usage,
                    "output_tokens",
                    None,
                )
                if usage
                else None,

            "total_tokens":
                getattr(
                    usage,
                    "total_tokens",
                    None,
                )
                if usage
                else None,

            "response_id":
                getattr(
                    response,
                    "id",
                    None,
                ),
        }

        return (
            lesson,
            usage_data,
        )

    except AIServiceError:
        raise

    except Exception as exc:
        raise AIServiceError(
            "Không tạo được lesson từ OpenAI: "
            f"{exc}"
        ) from exc


def build_visual_prompt(
    sentence: str,
    context_key: str,
    visual_spec: dict[str, Any],
    base_prompt: str,
    correction: str = "",
) -> str:

    contract = json.dumps(
        visual_spec or {},
        ensure_ascii=False,
    )

    extra = (
        "\nCORRECTION FROM PREVIOUS QA: "
        + correction
        if correction
        else ""
    )

    return f"""
Create ONE educational illustration that makes this exact
English sentence understandable without translation.

EXACT SENTENCE:
{sentence}

CONTEXT:
{context_key}

SCENE CONTRACT:
{contract}

BASE DIRECTION:
{base_prompt}

Fidelity rules:

1. Show every must_show item clearly and literally.
2. The exact action/relation in the sentence must be visually unambiguous.
3. Do not add objects/actions that could imply a different sentence.
4. No text, captions, labels, speech bubbles, UI words,
   brand logos or watermark.
5. Keep composition simple with one focal action.
6. Educational, clean, realistic illustration.
7. Do not visualize a translation.
8. Visualize the English meaning itself.

{extra}
""".strip()


def generate_visual_image(
    prompt: str,
) -> tuple[
    bytes,
    dict[str, Any],
]:

    client = _client()

    try:

        result = client.images.generate(
            model=image_model_name(),

            prompt=prompt,

            quality=image_quality(),

            size=image_size(),

            output_format="webp",

            output_compression=
                image_compression(),

            background="opaque",
        )

        if (
            not getattr(
                result,
                "data",
                None,
            )
            or not getattr(
                result.data[0],
                "b64_json",
                None,
            )
        ):
            raise AIServiceError(
                "Image model không trả về ảnh."
            )

        raw = base64.b64decode(
            result.data[0].b64_json
        )

        usage = getattr(
            result,
            "usage",
            None,
        )

        input_details = (
            getattr(
                usage,
                "input_tokens_details",
                None,
            )
            if usage
            else None
        )

        output_details = (
            getattr(
                usage,
                "output_tokens_details",
                None,
            )
            if usage
            else None
        )

        usage_data = {
            "response_id":
                getattr(
                    result,
                    "id",
                    None,
                ),

            "input_tokens":
                getattr(
                    usage,
                    "input_tokens",
                    None,
                )
                if usage
                else None,

            "cached_input_tokens":
                getattr(
                    input_details,
                    "cached_tokens",
                    0,
                )
                if input_details
                else 0,

            "output_tokens":
                getattr(
                    usage,
                    "output_tokens",
                    None,
                )
                if usage
                else None,

            "image_input_tokens":
                getattr(
                    input_details,
                    "image_tokens",
                    0,
                )
                if input_details
                else 0,

            "image_output_tokens":
                getattr(
                    output_details,
                    "image_tokens",
                    0,
                )
                if output_details
                else 0,

            "total_tokens":
                getattr(
                    usage,
                    "total_tokens",
                    None,
                )
                if usage
                else None,
        }

        return (
            raw,
            usage_data,
        )

    except AIServiceError:
        raise

    except Exception as exc:
        raise AIServiceError(
            "Không sinh được hình AI: "
            f"{exc}"
        ) from exc


def check_visual_match(
    sentence: str,
    visual_spec: dict[str, Any],
    image_bytes: bytes,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:

    client = _client()

    data_url = (
        "data:image/webp;base64,"
        + base64.b64encode(
            image_bytes
        ).decode("ascii")
    )

    prompt = (
        f"Exact sentence: {sentence}\n"
        "Scene contract: "
        + json.dumps(
            visual_spec or {},
            ensure_ascii=False,
        )
        + "\nEvaluate semantic fidelity "
        "of the supplied image."
    )

    try:

        response = client.responses.create(
            model=vision_model_name(),

            instructions=
                VISUAL_CHECK_INSTRUCTIONS,

            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type":
                                "input_text",

                            "text":
                                prompt,
                        },
                        {
                            "type":
                                "input_image",

                            "image_url":
                                data_url,

                            "detail":
                                "low",
                        },
                    ],
                }
            ],

            store=False,

            text={
                "format": {
                    "type":
                        "json_schema",

                    "name":
                        "visual_semantic_check",

                    "description":
                        "Semantic QA for a "
                        "generated learning image.",

                    "schema":
                        VISUAL_CHECK_SCHEMA,

                    "strict":
                        True,
                }
            },
        )

        if not response.output_text:
            raise AIServiceError(
                "Vision QA không trả về kết quả."
            )

        result = json.loads(
            response.output_text
        )

        usage = getattr(
            response,
            "usage",
            None,
        )

        details = (
            getattr(
                usage,
                "input_tokens_details",
                None,
            )
            if usage
            else None
        )

        usage_data = {
            "response_id":
                getattr(
                    response,
                    "id",
                    None,
                ),

            "input_tokens":
                getattr(
                    usage,
                    "input_tokens",
                    None,
                )
                if usage
                else None,

            "cached_input_tokens":
                getattr(
                    details,
                    "cached_tokens",
                    0,
                )
                if details
                else 0,

            "output_tokens":
                getattr(
                    usage,
                    "output_tokens",
                    None,
                )
                if usage
                else None,

            "total_tokens":
                getattr(
                    usage,
                    "total_tokens",
                    None,
                )
                if usage
                else None,
        }

        return (
            result,
            usage_data,
        )

    except AIServiceError:
        raise

    except Exception as exc:
        raise AIServiceError(
            "Không kiểm tra được độ khớp hình: "
            f"{exc}"
        ) from exc


def save_visual_file(
    image_bytes: bytes,
    directory: str,
    filename: str,
) -> str:

    path = Path(directory)

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    full = (
        path
        / filename
    )

    full.write_bytes(
        image_bytes
    )

    return str(full)


def test_openai_connection(
    api_key: str | None = None,
    text_model: str | None = None,
    image_model: str | None = None,
    vision_model: str | None = None,
) -> dict[str, Any]:

    """
    Test API key + model access.

    It retrieves model metadata instead of creating
    a lesson or image.
    """

    client = _client(
        api_key=api_key
    )

    models = {
        "text":
            text_model
            or model_name(),

        "image":
            image_model
            or image_model_name(),

        "vision":
            vision_model
            or vision_model_name(),
    }

    results: dict[
        str,
        Any
    ] = {}

    for (
        name,
        model_id,
    ) in models.items():

        try:

            model = (
                client.models.retrieve(
                    model_id
                )
            )

            results[name] = {
                "ok":
                    True,

                "model":
                    getattr(
                        model,
                        "id",
                        model_id,
                    ),
            }

        except Exception as exc:

            results[name] = {
                "ok":
                    False,

                "model":
                    model_id,

                "error":
                    str(exc),
            }

    return {
        "ok":
            all(
                item["ok"]
                for item
                in results.values()
            ),

        "models":
            results,
    }