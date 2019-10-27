# Freight for Alliance Auth

This is a plugin app for [Alliance Auth](https://gitlab.com/allianceauth/allianceauth) (AA) that adds an alliance Freight service.

![License](https://img.shields.io/badge/license-MIT-green) ![python](https://img.shields.io/badge/python-3.5-informational) ![django](https://img.shields.io/badge/django-2.2-informational)

**Status**: In Development

## Overview

This app helps running a central freight service for an alliance. The main concept of such a freight service is as follows:

- Every alliance member can create courier contracts to the alliance for defined routes

- Courier contracts have a reward according to the official pricing for that route and sufficient collateral to prevent scamming

- Every interested alliance member can pick up and deliver existing courier contracts

## Key Features

To support this concept Alliance Freight offers the following main features:

- Reward calculator allowing  members to easily calculate the correct reward for their a courier contract

- Page showing the list of currently outstanding courier contracts incl. an indicator  if the contract is compliant with the pricing for the respective route

- Multiple routes can be defined, each with its own pricing

- Automatic notification to a Discord channel about new courier contracts

## Screenshots

### Reward Calculator

![calculator](https://i.imgur.com/2PTXo9N.png)

### Contract List

![contract list](https://i.imgur.com/E5ZEGuM.png)

### Discord Notification

![notification](https://i.imgur.com/ynWnW0o.png)

## Installation

### 1. Install app

Install into AA virtual environment with PIP install from this repo:

```bash
pip install git+https://gitlab.com/ErikKalkoken/aa-freight.git
```

### 2 Update Eve Online app

Update the Eve Online app used for authentication in your AA installation to include the following scopes:

```plain
esi-universe.read_structures.v1
esi-contracts.read_corporation_contracts.v1
```

### 3. Configure AA settings

Configure your AA settings (`local.py`) as follows:

- Add `'freight'` to `INSTALLED_APPS`
- Add these lines add to bottom of your settings file:

   ```python
   # settings for standingssync
   CELERYBEAT_SCHEDULE['freight_run_contracts_sync'] = {
       'task': 'freight.tasks.run_contracts_sync',
       'schedule': crontab(minute='*/10'),
   }
   ```

If you want to setup notifications for Discord you can now also add the required settings. Check out section **Settings** for details.

### 4. Finalize installation into AA

Run migrations & copy static files

```bash
python manage.py migrate
python manage.py collectstatic
```

Restart your supervisor services for AA

### 5. Setup permissions

Now you can access Alliance Auth and setup permissions for your users. See section **Permissions** below for details.

### 6. Setup contract handler

Finally you need to set the contract handler with the alliance character that will be used for fetching the alliance contracts and related structures. Just click on "Set Contract Handler" and add the requested token. Note that only users with the appropriate permission will be able to see and use this function.

Once a contract handler is set the app will start fetching alliance contracts. Wait a minute and then reload the contract list page to see the result.

### 7. Define pricing

Finally go ahead and define the first pricing of a courier route. See section **Pricing** for details.

That's it. The Alliance Freight app is fully installed and ready to be used.

## Settings

Here is a list of available settings for this app. They can be configured by adding them to your AA settings file (`local.py`). If they are not set the defaults are used.

Name | Description | Default
-- | -- | --
`FREIGHT_DISCORD_WEBHOOK_URL`| Webhook URL for the Discord channel where contract notifications should appear | Not defined = Deactivated
`FREIGHT_DISCORD_AVATAR_URL`| URL to an image file to override the default avatar on Discord notifications, which is the Eve alliance logo | Alliance logo
`FREIGHT_DISCORD_PING_TYPE`| Defines if and how notifications will ping on Discord by adding mentions: Valid values are: `@here` or `@everyone`  | Not defined = No ping

## Permissions

This is an overview of all permissions used by this app:

Name | Purpose | Code
-- | -- | --
Can add / update locations | User can add and update Eve Online contract locations, e.g. stations and upwell structures |  `add_location`
Can access this app |Enabling the app for a user. This permission should be enabled for everyone who is allowed to use the app (e.g. Member state) |  `basic_access`
Can setup contract handler | Add or updates the alliance character for syncing contracts. This should be limited to users with admins / leadership privileges. |  `setup_contract_handler`
Can use the calculator | Enables using the calculator page the app. This permission is usually enabled for every alliance member. |  `use_calculator`
Can view the contracts list | Enables viewing the page with all outstanding courier contracts  |  `view_contracts`

## Pricing

A pricing defines a route and the parameters for calculating the price for that route along with some additional information for the users. You can define multiple pricings if you want, but at least one pricing has to be defined for this app to work.

Pricing routes are bidirectional, so it does not matter which location is chosen as start and which as destination when creating a courier contract.

Pricings are defined in the admin section of AA, so you need staff permissions to access it.

Most parameters of a pricing are optional, but you need to define at least one of the four pricing components to create a valid pricing. It's also possible to define a route that does not require a reward by setting "Price base" to 0 and not setting any other pricing components.

Parameter | Description | Pricing Functionality
-- | -- | --
Start Location | Starting station or structure for courier route | -
End Location | Destination station or structure for courier route  | -
Active | Non active pricings will not be used or shown | -
Price base | Base price in ISK. If this is the only defined pricing component it will be shown as "Fix price" in the calculator. | Pricing component
Price min | Minimum total price in ISK | Pricing component
Price per volume | Add-on price per m3 volume in ISK | Pricing component
Price per collateral_percent | Add-on price in % of collateral | Pricing component
Collateral min | Minimum required collateral in ISK | Validation check
Collateral max | Maximum allowed collateral in ISK | Validation check
Volume min | Minimum allowed volume in m3 | Validation check
Volume max | Maximum allowed volume in m3 | Validation check
Days to expire | Recommended days for contracts to expire | Info
Days to complete | Recommended days for contract completion | Info
Details | Text with additional instructions for using this pricing | Info

> **Adding Locations**:<br>If you are creating a pricing for a new route or this is the first pricing you are creating you may need to first add the locations (stations and/or structures) to the app. The best way is add new locations is with the "Add Location" feature on the main page of the app. Alternatively you can just create a courier contract between those locations in game. They will be added automatically when the contract is synced by Alliance Freight.
