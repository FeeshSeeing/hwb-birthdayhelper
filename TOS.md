# HWB-BirthdayHelper Terms of Service (TOS)

**Last Updated:** 2025-09-12

## 1. Introduction
HWB-BirthdayHelper is a hobby project designed to manage and announce birthdays in Discord servers. By using the bot, you agree to these Terms of Service.  

If you do not agree, do not use HWB-BirthdayHelper.

## 2. Usage Rules
- Use HWB-BirthdayHelper responsibly and within Discord's Terms of Service.  
- Provide accurate information when setting birthdays (`/setbirthday` or `/setuserbirthday`).  
- Ensure that roles and channels used by the bot exist and that the bot has proper permissions.

## 3. Data Collection
- HWB-BirthdayHelper stores only the following:
  - User IDs
  - Birthday dates
  - Optional server configuration (roles, channels, check hour)
- Data is stored **locally** in a SQLite database (`birthdays.db`).  
- No data is shared externally or sold.

## 4. Permissions
- Optional permissions may be requested by the bot:
  - **Manage Messages**: To pin/unpin birthday messages.  
  - **Manage Roles**: To assign/remove birthday roles.
- These permissions are optional; the bot will still function with limited access but some features may not work fully.

## 5. Admins and Moderators
- Commands like `/setuserbirthday`, `/deleteuserbirthday`, and `/testdate` are **restricted to admins or users with a configured mod role**.  
- Regular users can only manage their own birthdays.

## 6. Liability
- HWB-BirthdayHelper is provided **as-is**.  
- The developer is not responsible for:
  - Loss of birthday data
  - Role misassignments
  - Any other issues caused by using the bot  
- Use the bot at your own risk.

## 7. Updates
- HWB-BirthdayHelper may receive updates, new features, or bug fixes at any time.  
- Features, data storage, or commands may change in future versions without notice.

## 8. Deletion and Termination
- Server admins can remove HWB-BirthdayHelper from their server at any time.  
- Users can delete their birthdays with `/deletebirthday`.  
- Admins can remove other users' birthdays with `/deleteuserbirthday`.

## 9. Contact
For questions, bug reports, or concerns about these Terms of Service, contact the developer via Discord or the project repository.

---

By using HWB-BirthdayHelper, you acknowledge that you have read, understood, and agreed to this Terms of Service.
