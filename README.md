# HWB Birthday Helper

...

## GDPR Compliance
HWB Birthday Helper respects your privacy and follows the GDPR regulations. Below is how your data is handled:

### Data Collected
- **User ID** (`discord.User.id`): To identify users for their birthdays.
- **Guild ID** (`discord.Guild.id`): To store birthdays per server.
- **Birthday** (month-day format, e.g., `12-25`): The only personal data stored.

### Purpose
- To display and send birthday messages on the correct day.
- To pin and update birthday lists in Discord channels.

### Storage
- Data is stored locally in an SQLite database (`birthdays.db`) on the host machine.
- No data is sent to any external servers.

### Retention
- Data is retained until the user deletes their birthday or the guild removes the bot.

### User Rights
- **Right to access:** Users can see their stored birthday using `/listbirthdays`.
- **Right to deletion:** Users can delete their birthday with `/deletebirthday`.
- **Right to modify:** Users can change their birthday with `/setbirthday`.

### Security
- Only the bot and Discord administrators (if configured) can see or modify this data.
- Birthday roles are assigned optionally and only on the user's birthday.

### Contact
- Users can request full deletion of their data by contacting the server administrator or the bot owner directly.
