"""Versioned public-facing creative rules for the Mr.Who? persona."""

MR_WHO_STYLE = {
    "style_id": "mr-who-shortform",
    "style_version": "1.0.0",
    "language": "pt-BR",
    "tone": ["curious", "clear", "energetic", "light_mystery", "intelligent"],
    "hook_families": ["curiosity", "unexpected_fact", "challenge", "comparison",
                       "visual_surprise", "question", "contrarian_angle", "before_after", "mini_story", "open_loop"],
    "pacing_rules": {"target_seconds": [12, 28], "opening_seconds_max": 2.5,
                     "scene_change_seconds_max": 5.0},
    "scene_rules": {"minimum": 4, "prefer_distinct_compositions": True},
    "caption_rules": {"short_phrases": True, "maximum_words_per_block": 14,
                       "burned_in_and_srt": True, "safe_zone_top_bottom_percent": 12},
    "motion_rules": {"camera_motion_required": True, "transition_required": True},
    "narration_rules": {"language": "pt-BR", "truthful_fallback": True},
    "visual_rules": {"original_or_licensed_assets_only": True, "avoid_static_slideshow": True},
    "audio_rules": {"music_rights_required": True, "narration_may_be_unavailable": True},
    "cta_rules": {"one_clear_action": True, "no_follow_or_engagement_claims" : True},
    "forbidden_patterns": ["watermark_removal", "copied_viral_video", "long_scrolling_paragraph",
                            "invented_metrics", "fake_engagement", "childish_mascot_tone"],
}

HOOK_FAMILIES = tuple(MR_WHO_STYLE["hook_families"])
