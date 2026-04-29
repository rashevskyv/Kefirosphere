# [KEFIR 814 ![GitHub Downloads (specific asset, all releases)](https://img.shields.io/github/downloads/rashevskyv/kefir/kefir814.zip)](https://github.com/rashevskyv/kefir/releases/download/814/kefir814.zip)

<img width="1280" height="720" alt="kefir" src="https://github.com/rashevskyv/kefir/releases/download/814/kefir.png" />


## Changelog 
#### **UKR**
**Повна підтримка 22.1.0**

**814**
* [**Додано**] Файл '/config/.skip' має список файлів та папок які будуть виключені з примусової перевірки атрибутів при оновленні кефіра через kefir-updater
* [**Оновлено**] [`Homebrew menu [03DB12780BD84000][v0].nsp`] — Обов'язково перевстановіть 'games/Homebrew menu [03DB12780BD84000][v0].nsp' через DBI як гру, якщо користуєтесь форвардером для запуска HBL з головного екрану 
* [**Оновлено**] [Ovl Sysmodules v1.4.9](https://github.com/ppkantorski/ovl-sysmodules/releases/tag/v1.4.9) — Ліміт нейтральної пам'яті підвищено з 4 МБ до 5 МБ.
* [**Оновлено**] [Sys Patch v1.6.1](https://github.com/borntohonk/sys-patch/releases/tag/v1.6.1) — Додано захоплення зсуву в логах та накладенні, а також виправлено виявлення "прошитого за файлом" і "прошитого за системним патчем".

**813**
* [**Оновлено**] [Sys Patch v1.6.0](https://github.com/impeeza/sys-patch/releases/tag/v1.6.0) — Основна зміна - рефакторинг коду та виправлення для версії 22.0.0.
* [**Додано**] При оновленні кефіру ключі знімаються автоматично 

**809**
* [**Оновлено**] [Atmosphere 1.11.1](https://github.com/rashevskyv/Kefirosphere) - Реліз. Підтримка прошивки 22.1.0. 
    * [**Подробиці про зміни в Atmosphere**](https://github.com/Atmosphere-NX/Atmosphere/releases) 
* [**Оновлено**] [Mission Control 0.15.1](https://github.com/ndeadly/MissionControl/releases/tag/v0.15.1) - Підтримка прошивки 22.1.0. 
____

#### **ENG**
**Full support for 22.1.0**

**814**
* [**Added**] The file '/config/.skip' contains a list of files and folders that will be excluded from forced attribute checks when updating kefir via kefir-updater.
* [**Updated**] [`Homebrew menu [03DB12780BD84000][v0].nsp`] — Be sure to reinstall 'games/Homebrew menu [03DB12780BD84000][v0].nsp' via DBI as a game if you are using a forwarder to launch HBL from the home screen.
* [**Updated**] [Ovl Sysmodules v1.4.9](https://github.com/ppkantorski/ovl-sysmodules/releases/tag/v1.4.9) — The neutral memory limit has been increased from 4 MB to 5 MB.
* [**Updated**] [Sys Patch v1.6.1](https://github.com/borntohonk/sys-patch/releases/tag/v1.6.1) — Added shift capturing in logs and overlays, as well as fixed detection of "flashed by file" and "flashed by system patch."

**813**
* [**Updated**] [Sys Patch v1.6.1](https://github.com/borntohonk/sys-patch/releases/tag/v1.6.1) — Added offset capture in logs and overlay, and fixed detection of "patched-by-file" versus "patched-by-sys-patch".
* [**Updated**] [Ovl Sysmodules v1.4.9](https://github.com/ppkantorski/ovl-sysmodules/releases/tag/v1.4.9) — The neutral memory limit has been raised from 4MB to 5MB.
* [**Updated**] [Sys Patch v1.6.0](https://github.com/impeeza/sys-patch/releases/tag/v1.6.0) — The key change is a code refactor and fixes for version 22.0.0.
* [**Added**] Auto dump keys after kefir update

**809**
* [**Updated**] [Atmosphere 1.11.1](https://github.com/rashevskyv/Kefirosphere) - Release. Firmware 22.1.0 support.
    * [**More details about changes in Atmosphere**](https://github.com/Atmosphere-NX/Atmosphere/releases)
* [**Updated**] [Mission Control 0.15.1](https://github.com/ndeadly/MissionControl/releases/tag/v0.15.1) - Firmware 22.1.0 support.

______

![telegram](https://github.com/user-attachments/assets/da539e4c-322e-4ba7-b191-01056246cc36)
https://t.me/kefir_ukr

Це збірка, яка складається з модифікованої Atmosphere, необхідних програм та скриптів, які все це встановлюють правильним чином. Її було придумано для полегшення встановлення та обслуговування програмного забезпечення на взломаній Nintendo Switch. Зміни, внесені в Atmosphere направлені на збільшення якості досвіду користування самою системою.

**Зміни відносно ванільної Atmosphere**:

* Версії кефіру біля версії системи
* Встановлення певного драйверу карти пам'яті за замовчуванням при оновленні системи
* Видалення перевірки ACID-підпису для використання хомбрю без патчів
* Видалення логіювання всього системою для запобігання засмітнення картки пам'яті та надмірного її використання
* Перенаправлення сейвів з внутрішньої пам'яті на карту пам'яті при використанні емунанду, щоб зменшити вірогідність їх втрати при виходу емунанду з ладу (опційно)
* Вбудовані сігпатчі

**English**:

This is a bundle that consists of a modified Atmosphere, necessary programs and scripts that all install correctly. It was designed to make it easier to install and maintain software on a hacked Nintendo Switch. The changes made to Atmosphere are aimed at improving the quality of the user experience.

**Kefirosphere features**:

* Updating the firmware version to match the system version
* Installing a specific memory card driver by default when updating the system
* Removing the ACID signature check for using homebrew without patches
* Removing system logging to prevent cluttering the memory card and excessive use
* Redirecting saves from internal memory to the memory card when using the emuNAND command to reduce the likelihood of losing them when exiting the emuNAND command (optional)
* Built-in sigpatches

[Склад / Consistent](https://switch.customfw.xyz/kefir#%D1%81%D0%BE%D1%81%D1%82%D0%B0%D0%B2-kefir)

___

## Як встановити або оновити кефір / How to install or update kefir

**Встановлення та оновлення кефіру відбувається однаково!**

_Якщо ви є користувачем MacOS, використовуйте [ці рекомендації](https://switch.customfw.xyz/sd-macos), щоб уникнути проблем з картою пам'яті_

**Щоб потрапити в hekate прошитій приставці, перезавантажте консоль, на заставці кефіра натисніть кнопку зниження гучності.** Попавши в hekate, можете витягувати карту пам'яті. Після того як ви знову вставите картку в консоль, запустіть прошивку через меню Launch -> Atmosphere.

**English**:

**Installing and updating kefir is done the same way!**

_If you are a MacOS user, use [these recommendations](https://switch.customfw.xyz/sd-macos) to avoid problems with the memory card_

**To get into hekate on a firmware-flashed device, reboot the console, on the kefir splash screen press the volume down button.** Once in hekate, you can extract the memory card. After reinserting the card into the console, launch the firmware through the menu Launch -> Atmosphere.

___

### Для всіх ОС / For all OS

1. Скопіюйте в корінь карти пам'яті **вміст архіву** `kefir.zip`
    * **НЕ САМ АРХІВ, ЙОГО ВМІСТЬ!**
2. Вставте картку пам'яті назад у Switch
3. У **hekate** виберіть `More configs` -> `Update Kefir`
4. Після закінчення встановлення приставка запуститься у прошивку

**English**:

1. Copy the contents of the `kefir.zip` archive **to the root** of the memory card
    * **NOT THE ARCHIVE ITSELF, ITS CONTENTS!**
2. Insert the memory card back into the Switch
3. In **hekate** select `More configs` -> `Update Kefir`
4. After installation is complete, the device will boot into the firmware

### Тільки для Windows, також якщо попередній метод не спрацював / Only for Windows, also if the previous method did not work

1. Розпакуйте на ПК архів `kefir.zip`
2. Запустіть `install.bat` з розпакованого архіву та дотримуйтесь вказівок на екрані
3. Коли ви побачите на екрані напис "**All Done**", вставте картку пам'яті назад у консоль і запустіть прошивку

**English**:

1. Extract the `kefir.zip` archive on your PC
2. Run `install.bat` from the extracted archive and follow the on-screen instructions
3. When you see the message "**All Done**" on the screen, insert the memory card back into the console and start the firmware

## Можливі помилки / Possible errors

* У разі виникнення помилки "**Is BEK missing**" вимкніть приставку та увімкніть заново
* У разі виникнення помилки "**[NOFAT]**" при оновленні кефіру через гекату, оновіть його за допомогою `install.bat`
* У разі виникнення помилки "**Failed to match warmboot with fuses**", перезагрузіть консоль в **hekate** -> **More configs** -> **Full Stock**, або оновіть emunand до останньої версії
* Якщо виникають будь-які інші помилки, зверніться до розділу "[Проблеми та рішення посібника](https://switch.customfw.xyz/troubleshooting)"

**English**:

* In case of the "**Is BEK missing**" error, turn off the console and turn it on again
* In case of the "**[NOFAT]**" error when updating kefir through hekate, update it using `install.bat`
* If you receive the error "**Failed to match warmboot with fuses**" when launching Emunand, reboot the console in **hekate** -> **More configs** -> **Full Stock** or update the Emunand to the latest version.
* If any other errors occur, please refer to the "[Troubleshootings](https://switch.customfw.xyz/troubleshooting)" section of the guide
