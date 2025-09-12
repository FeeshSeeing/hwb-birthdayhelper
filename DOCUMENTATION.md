🎂 **BirthdayBot Cheat Sheet**

==============================

**User Commands**
----------------
`/setbirthday day:<day> month:<month>`  
> Set your birthday. Example: `/setbirthday day:25 month:12`

`/deletebirthday`  
> Delete your birthday.

`/listbirthdays`  
> Refresh the pinned birthday list.

==============================

**Admin / Moderator Commands**
------------------------------
`/setuserbirthday user:@User day:<day> month:<month>`  
> Set another user's birthday.

`/deleteuserbirthday user:@User`  
> Delete another user's birthday.

`/importbirthdays channel:#channel message_id:<id>`  
> Import birthdays from a message.

==============================

**Server Setup**
----------------
`/setup channel:#birthdays birthday_role:@Birthday mod_role:@Mod check_hour:<0-23>`  
> Configure the bot for your server.

Notes:
- `birthday_role` is optional, bot assigns it on birthdays if set.  
- `mod_role` is optional, if not set, only admins can manage birthdays.  
- `check_hour` is **GMT+0**, determines the announcement hour.

==============================

**🎯 Testing Birthdays with /testdate**

- **Command:** `/testdate day:<day> month:<month> [year:<year>]`
  - Simulates birthday messages for a specific date (GMT+0)
  - Example 1: `/testdate day:28 month:02` → simulate Feb 28 of the current year
  - Example 2: `/testdate day:29 month:02 year:2024` → simulate Feb 29 of a leap year
  - Resets the "already wished" tracker so all users can be wished again
  - Automatically handles birthday role assignment and removal

> ⚠ **Access:** Admins or users with the configured mod role (if set)
> ✅ Fully handles birthdays, including Feb 29, with proper role management

==============================

**Time Zone Note**
-----------------
- All scheduled times (`check_hour`) are based on **GMT+0**.
- Example: If you set `/setup check_hour:9`, birthday messages will be sent at 09:00 UTC.
- This ensures consistent behavior across all servers worldwide.


**Tips & Notes**
----------------
- 🎯 All scheduled times (`check_hour`) are **GMT+0**.
- ⚠ **Manage Messages** required for pinned birthday messages. Without it, birthdays announce but pins won’t update.
- 🛡 **Manage Roles** required for birthday role assignment (optional if not configured).
- Feb 29 birthdays are handled: non-leap years default to Feb 28.
- Pinned birthday list shows **upcoming birthdays first**.

