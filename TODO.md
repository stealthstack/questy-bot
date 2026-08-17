# Refactor Duplicate Code in speedrun_bot.py

## Plan
- Create helper functions to eliminate duplicate code
- Refactor commands to use the helpers

## Steps
- [x] Create `create_composite_image(images, filename, gap=0)` helper
- [x] Create `create_record_embed(record)` helper
- [ ] Refactor `speedrun` command to use `create_record_embed`
- [ ] Refactor `collection` command to use `create_record_embed`
- [ ] Refactor `dailypot` command to use `create_record_embed`
- [ ] Refactor `devpot` command to use `create_record_embed`
- [ ] Test the refactored code
