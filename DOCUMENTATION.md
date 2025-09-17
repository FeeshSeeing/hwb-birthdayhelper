**🎉 HWB-BirthdayHelper Documentation**

---

**1️⃣ Commands**

- `/setbirthday day:<day> month:<month>`  
  Set your own birthday. Example: `/setbirthday day:25 month:12`  

- `/deletebirthday`  
  Delete your own birthday.

- `/listbirthdays`  
  Refreshes and pins the birthday list.

- `/setuserbirthday user:<user> day:<day> month:<month>`  
  **Admin/Mod only**: Set a birthday for another user.

- `/deleteuserbirthday user:<user>`  
  **Admin/Mod only**: Delete a user's birthday.

- `/setup channel:<channel> [birthday_role:<role>] [mod_role:<role>] [check_hour:<0-23>]`  
  Configure bot for your server. Optional:
  - Birthday role: assigned on birthdays  
  - Mod role: allowed to manage birthdays  
  - Check hour: GMT+0 hour for daily birthday messages  

- `/testdate day:<day> month:<month> [year:<year>]`  
  **Admin/Mod only**: Simulate birthday messages for a specific date (GMT+0)  
  Example: `/testdate day:29 month:02 year:2024`  

---

**2️⃣ Birthday Role and Bot Hierarchy**

- BirthdayBot **must have a role above the birthday role** to assign/remove it.  
- Optional permissions:
  - `Manage Roles`: needed to assign/remove birthday roles  
  - `Manage Messages`: needed to pin/update birthday messages  

**Recommended setup:**
1. Create a bot role (e.g., `BirthdayBot`).  
2. Move it **above the birthday role** in the server settings.  
3. Grant optional permissions.  
4. Configure roles via `/setup`.

---

**3️⃣ Admin/Mod Access**

- Admins or users with the configured mod role can use:
  - `/setuserbirthday`  
  - `/deleteuserbirthday`  
  - `/testdate`  
- Regular users can only manage their own birthdays with `/setbirthday` and `/deletebirthday`.

---

**4️⃣ Birthday Handling**

- **GMT+0** is used for all birthday checks.  
- Birthday messages are automatically sent at the configured check hour.  
- Feb 29 birthdays are automatically announced on Feb 28 in non-leap years.  
- Pinned birthday messages are updated after adding, removing, or changing birthdays.  

---

**5️⃣ Data Storage**

- Stores user IDs, birthdays, and optional guild configuration (roles, channels, check hour).  
- Data is stored locally in `birthdays.db`.  
- No personal data is shared externally.  

---

**6️⃣ Notes and Limitations**

- Use the bot responsibly and within Discord TOS.  
- If the bot cannot assign/remove roles or pin messages, check role hierarchy and permissions.  
- `/testdate` resets the daily tracker so all users can be wished again.  





# 📋 HWB-BirthdayHelper Command Permissions

| Command            | Visible To          | Who Can Use It?             | Notes |
|--------------------|---------------------|-----------------------------|------|
| `/setup`           | Admins only         | Admins only                 | Used once per server to configure bot |
| `/setuserbirthday` | Admins + Mods       | Admins + Mods               | Set birthdays for other users |
| `/deleteuserbirthday` | Admins + Mods    | Admins + Mods               | Delete birthdays for other users |
| `/importbirthdays` | Admins + Mods       | Admins + Mods               | Bulk import birthdays from a message |
| `/wipeguild`       | Admins + Mods       | Admins + Mods               | **Dangerous**: wipes all birthdays & config |
| `/testdate`        | Admins + Mods       | Admins + Mods               | Run a birthday check for a custom date (for testing) |
| `/showwished`      | Admins + Mods       | Admins + Mods               | Shows which users have been wished today |
| `/clearwished`     | Admins + Mods       | Admins + Mods               | Clears the "wished today" list (for testing) |
| `/setbirthday`     | Everyone            | Everyone                    | Users set their own birthdays |
| `/mybirthday`      | Everyone            | Everyone                    | Users can view their saved birthday |
| `/listbirthdays`   | Everyone            | Everyone                    | Show a list of all birthdays in the server |

> ✅ **Admins** = Discord users with Administrator permission  
> ✅ **Mods** = Users with the moderator role you set during `/setup`  
> 👀 **Visibility** = These commands won't even show up in the slash-command list for users who don't have permission
