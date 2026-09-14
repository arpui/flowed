# Data Examples Directory

This directory contains **template files** showing the structure of the learning data that will be created in `/data` when you run `/fluent-setup`.

## 📋 Template Files

| Template File | What It Becomes | Purpose |
|--------------|-----------------|---------|
| `learner-profile-template.json` | `/data/learner-profile.json` | Your personal info, goals, preferences |
| `progress-db-template.json` | `/data/progress-db.json` | Statistics and accuracy trends |
| `mistakes-db-template.json` | `/data/mistakes-db.json` | Error patterns you're working on |
| `mastery-db-template.json` | `/data/mastery-db.json` | Skill mastery levels (0-5 stars) |
| `spaced-repetition-template.json` | `/data/spaced-repetition.json` | Review schedule (SM-2 algorithm) |
| `session-log-template.json` | `/data/session-log.json` | Complete session history |

## 🎯 Purpose

**These templates are for reference only!**

- ✅ **See the data structure** before running `/fluent-setup`
- ✅ **Understand what gets tracked** in each database
- ✅ **For developers** who want to understand the schema
- ✅ **For contributors** building integrations or tools

## 🚫 Don't Use These Directly

**Do NOT copy these to `/data`!**

The `/fluent-setup` command will create the actual files with:
- ✅ Your real information (name, language, goals)
- ✅ Initialized values (0s, empty arrays)
- ✅ Today's date as creation date
- ✅ Proper metadata

## 📖 How to Read Templates

Templates use placeholders:

```json
{
  "learner": {
    "name": "{YOUR_NAME}",
    "target_language": "{LANGUAGE_YOU_WANT_TO_LEARN}",
    "current_level": "{A1|A2|B1|B2|C1|C2}"
  }
}
```

**Placeholders explained:**
- `{YOUR_NAME}` - Will be your actual name
- `{YYYY-MM-DD}` - Will be actual dates
- `{A1|A2|B1|B2|C1|C2}` - Choose one of these options
- `{target_language}` - Your chosen language (Spanish, French, etc.)

## 🔍 Example: Learner Profile

**Template (what you see here):**
```json
{
  "learner": {
    "name": "{YOUR_NAME}",
    "target_language": "{LANGUAGE_YOU_WANT_TO_LEARN}"
  }
}
```

**Actual file (after `/fluent-setup`):**
```json
{
  "learner": {
    "name": "Sarah",
    "target_language": "Spanish"
  }
}
```

## 💡 For Developers

**Schema validation:**
- All templates follow the same structure as production data
- Use these for testing, documentation, or building tools
- Field types are documented in comments where needed

**Adding new fields:**
1. Update the template file here
2. Update the `/fluent-setup` command to populate it
3. Update AGENTS.md with the new structure
4. Update LEARNING_SYSTEM.md if it affects teaching

---

**Ready to create your actual data?** Run `/fluent-setup` to begin! 🚀

*Templates are for reference only. Your real data lives in `/data` (created automatically).*
