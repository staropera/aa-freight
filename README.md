# Freight for Alliance Auth

Freight is an [Alliance Auth](https://gitlab.com/allianceauth/allianceauth) (AA) app for running a freight service.

![release](https://img.shields.io/pypi/v/aa-freight?label=release) ![python](https://img.shields.io/pypi/pyversions/aa-freight) ![django](https://img.shields.io/pypi/djversions/aa-freight?label=django) ![pipeline](https://gitlab.com/ErikKalkoken/aa-freight/badges/master/pipeline.svg) ![coverage](https://gitlab.com/ErikKalkoken/aa-freight/badges/master/coverage.svg) ![license](https://img.shields.io/badge/license-MIT-green) ![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)

## Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Screenshots](#screenshots)
- [Installation](#installation)
- [Updating](#updating)
- [Settings](#settings)
- [Operation Mode](#operation-mode)
- [Permissions](#permissions)
- [Pricing](#pricing)
- [Contract Check](#contract-check)
- [Change Log](CHANGELOG.md)

## Overview

This app helps running a central freight service for an alliance or corporation. It allows different modes of operation that support the most common approaches a central freight service is setup. (e.g. for alliance members only or run by a corporation outside the alliance)

## Key Features

Freight offers the following main features:

- Reward calculator allowing members to easily calculate the correct reward for their a courier contract
- Page showing the list of currently outstanding courier contracts incl. an indicator if the contract is compliant with the pricing for the respective route ("contract check")
- Multiple routes can be defined, each with its own pricing.
- It's possible to have the same pricing for both directions, or to have different pricings for each direction of the same route.
- Automatic notifications to freight pilots on Discord informing them about new courier contracts
- Automatic notifications to contract issuers on Discord informing them about the developing status of their contract or potentially issues
- Contract issuer can always check the current status of his courier contracts
- Statistics page showing key performance metrics for routes, pilots, customers

## Screenshots

### Reward Calculator

![calculator](https://i.imgur.com/h9BZG4D.png)

### Contract List

![contract list](https://i.imgur.com/aJc6dwG.png)

### Discord Notification

![notification](https://i.imgur.com/ynWnW0o.png)

## Installation

### 1. Install app

Install into your Alliance Auth virtual environment from PyPI:

```bash
pip install aa-freight
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
   # settings for freight
   CELERYBEAT_SCHEDULE['freight_run_contracts_sync'] = {
       'task': 'freight.tasks.run_contracts_sync',
       'schedule': crontab(minute='*/10'),
   }
   ```

If you want to setup notifications for Discord you can now also add the required settings. Check out section **Settings** for details.

### 3a Celery setup

This app uses celery for critical functions like refreshing data from ESI. We strongly recommend to enable the following additional settings for celery workers to enable proper logging and to protect against potential memory leaks:

- To enable logging of celery tasks up to info level: `-l info`

- To automatically restart workers that grow above 256 MB: `--max-memory-per-child 262144`

Here is how an example config would look for workers in your supervisor conf:

```plain
command=/home/allianceserver/venv/auth/bin/celery -A myauth worker -l info --max-memory-per-child 262144
```

On Ubuntu you can run `systemctl status supervisor` to see where your supervisor config file is located.

Note that you need to restart the supervisor service itself to activate those changes.

e.g. on Ubuntu:

```bash
systemctl restart supervisor
```

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

Finally you need to set the contract handler with the character that will be used for fetching the corporation or alliance contracts and related structures. Just click on "Set Contract Handler" and add the requested token. Note that only users with the appropriate permission will be able to see and use this function. However, the respective character does not need any special corporation roles. Any corp member will work.

Once a contract handler is set the app will start fetching contracts. Wait a minute and then reload the contract list page to see the result.

### 7. Define pricing

Finally go ahead and define the first pricing of a courier route. See section **Pricing** for details.

That's it. The Freight app is fully installed and ready to be used.

## Updating

To update your existing installation of Freight first enable your virtual environment.

Then run the following commands from your AA project directory (the one that contains `manage.py`).

```bash
pip install -U aa-freight
```

```bash
python manage.py migrate
```

```bash
python manage.py collectstatic
```

Finally restart your AA supervisor services.

## Settings

Here is a list of available settings for this app. They can be configured by adding them to your AA settings file (`local.py`). If they are not set the defaults are used.

Name | Description | Default
-- | -- | --
`FREIGHT_APP_NAME`| Name of this app as shown in the Auth sidebar, page titles and as default avatar name for notifications. | `'Freight'`
`FREIGHT_CONTRACT_SYNC_GRACE_MINUTES`| Sets the number minutes until a delayed sync will be recognized as error  | `30`
`FREIGHT_DISCORD_DISABLE_BRANDING`| Turns off setting the name and avatar url for the webhook. Notifications will be posted by a bot called "Freight" with the logo of your organization as avatar image | `False`
`FREIGHT_DISCORD_MENTIONS`| Optional mention string put in front of every notification to create pings: Typical values are: `@here` or `@everyone`. You can also mention roles, however you will need to add the role ID for that. The format is: `<@&role_id>` and you can get the role ID by entering `_<@role_name>` in a channel on Discord. See [this link](https://www.reddit.com/r/discordapp/comments/580qib/how_do_i_mention_a_role_with_webhooks/) for details. | `''`
`FREIGHT_DISCORD_WEBHOOK_URL`| Webhook URL for the Discord channel where contract notifications for pilots should appear. | `None`
`FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL`| Webhook URL for the Discord channel where contract notifications for customers should appear. | `None`
`FREIGHT_FULL_ROUTE_NAMES`| Show full name of locations in route, e.g on calculator drop down  | `False`
`FREIGHT_HOURS_UNTIL_STALE_STATUS`| Defines after how many hours the status of a contract is considered to be stale. Customer notifications will not be sent for a contract status that has become stale. This settings also prevents the app from sending out customer notifications for old contracts. | `24`
`FREIGHT_OPERATION_MODE`| See section [Operation Mode](#operation-mode) for details.<br> Note that switching operation modes requires you to remove the existing contract handler with all its contracts and then setup a new contract handler | `'my_alliance'`
`FREIGHT_STATISTICS_MAX_DAYS`| Sets the number of days that are considered for creating the statistics  | `90`

## Operation Mode

The operation mode defines which contracts are processed by the Freight. For example you can define that only contracts assigned to your alliance are processed. Any courier contract that is  not in scope of the configured operation mode will be ignored by the freight app and e.g. not show up in the contract list or generate notifications.

The following operation modes are available:

Name | Description
-- | --
`'my_alliance'`| courier contracts assigned to configured alliance by an alliance member
`'my_corporation'`| courier contracts assigned to configured corporation by a corp member
`'corp_in_alliance'`| courier contracts assigned to configured corporation by an alliance member
`'corp_public'`| any courier contract assigned to the configured corporation

## Permissions

This is an overview of all permissions used by this app:

Name | Purpose | Code
-- | -- | --
Can add / update locations | User can add and update Eve Online contract locations, e.g. stations and upwell structures |  `add_location`
Can access this app |Enabling the app for a user. This permission should be enabled for everyone who is allowed to use the app (e.g. Member state) |  `basic_access`
Can setup contract handler | Add or updates the character for syncing contracts. This should be limited to users with admins / leadership privileges. |  `setup_contract_handler`
Can use the calculator | Enables using the calculator page and the "My Contracts" page. This permission is usually enabled for every user with the member state. |  `use_calculator`
Can view the contracts list | Enables viewing the page with all outstanding courier contracts  |  `view_contracts`
Can see statistics | User with this permission can view the statistics page  |  `view_statistics`

## Pricing

A pricing defines a route and the parameters for calculating the price for that route along with some additional information for the users. You can define multiple pricings if you want, but at least one pricing has to be defined for this app to work.

Pricing routes are bidirectional by default. For bidirectional pricings courier contracts in both directions are matched against the same pricing. Alternatively pricings can also be defined individually for each direction.

Pricings are defined in the admin section of AA, so you need staff permissions to access it.

Most parameters of a pricing are optional, but you need to define at least one of the four pricing components to create a valid pricing. It's also possible to define a route that does not require a reward by setting "Price base" to 0 and not setting any other pricing components.

All pricing parameters can be found on the admin panel under Pricing, with the exception of the "price per volume modifier", which is a global pricing parameter and therefore property of the ContractHandler.

Parameter | Description | Pricing Functionality
-- | -- | --
Start Location | Starting station or structure for courier route | -
End Location | Destination station or structure for courier route  | -
Is Active | Non active pricings will not be used or shown | -
Is Bidirectional | Wether this pricing shall apply to contracts for both directions of the route or only the specified direction | -
Price base | Base price in ISK. If this is the only defined pricing component it will be shown as "Fix price" in the calculator. | Pricing component
Price min | Minimum total price in ISK | Pricing component
Price per volume | Add-on price per m3 volume in ISK | Pricing component
Use price per volume modifier | Switch defining if the global price per volume modifier should be used for pricing | Pricing flag
Price per volume modifier | Global modifier for price per volume in percent. When used it will be added to the price per volume. It can be positive and negative, but the resulting price per volume can never be negative.<br>(defined for ContractHandler) | Pricing modifier
Price per collateral_percent | Add-on price in % of collateral | Pricing component
Collateral min | Minimum required collateral in ISK | Validation check
Collateral max | Maximum allowed collateral in ISK | Validation check
Volume min | Minimum allowed volume in m3 | Validation check
Volume max | Maximum allowed volume in m3 | Validation check
Days to expire | Recommended days for contracts to expire | Info
Days to complete | Recommended days for contract completion | Info
Details | Text with additional instructions for using this pricing | Info

> **How to add new locations**:<br>If you are creating a pricing for a new route you may need to first add the locations (stations and/or structures).<br>The easiest way is to create a courier contract between those locations in game and then run contract sync. Those locations will then be added automatically.<br>Alternatively you can use the "Add Location" feature on the main page of the app. This will require you to provide the respective station or structure eve ID.

## Contract Check

The app will automatically check if a newly issued contract complies with the pricing parameters for the respective route.

Compliant contracts will have a green checkmark (✓) in the "Contract Check" column on the contract list. Related notifications on Discord will be colored in green.

Non-compliant contracts will have a red warning sign in the "Contract Check" column on the contract list. And related notifications on Discord will be colored in red. In addition the first customer notification will inform the customer about the issues and ask him to correct the issues.

The following parameters will be checked (if they have been defined):

- reward in contract >= calculated reward
- volume min <= volume in contract <= volume max
- collateral min <= collateral in contract <= collateral max

Deviations on "Days to expire" and "Days to complete" are currently not part of the contract check and only used to show the recommended contract parameters in the calculator.
