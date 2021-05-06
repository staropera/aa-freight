# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased] - yyyy-mm-dd

### Added

- Ability to receive customer contract updates as direct messages on Discord via Discord Proxy
- Reward can not be copied to clipboard with on click

### Changed

- Rewards and collaterals are now shown in a humanized format in most places

Big thanks to @huideaki for contributing the direct messages feature!

## [1.4-0] - 2021-02-27

### Changed

- Removed support for Django 2
- Now uses the extensions logger
- Add pre-commit checks to CI
- Integrate codecov
- Migrate to allianceauth-app-utils

## [1.3-0] - 2020-11-19

### Added

- Volume now shown with statistics ([#32](https://gitlab.com/ErikKalkoken/aa-freight/issues/32))
- New view "All contracts"

### Changed

- Layout modernized and style aligned with other Kalkoken apps
- Numbers shown (e.g. reward, collateral) are no longer abbreviated

## [1.2.3] - 2020-10-24

### Changed

- Remove Django 3.0 from test matrix

### Fixed

- Side menu highlighting now works correctly

Thanks to Peter Pfeufer for the contribution!

## [1.2.2] - 2020-09-22

### Changed

- Applied "Staticfiles" fix to make it Django 3 compatible
- Extended test matrix with Django 3.x and core tests

## [1.2.1] - 2020-09-21

### Changed

- Removed dependency conflict with Auth regarding Django 3
- Improved Tox vs. setup dependencies

## [1.2.0] - 2020-09-17

### Added

- Now shows badge with count of outstanding contracts in side bar (only for uses who has that permission)
- Now shows badge with count of outstanding contracts in menu bar for "my contracts" and "active contracts"

### Fixed

- Will no longer try to install Django 3

## [1.1.4] - 2020-07-04

### Added

- Added ability to function with both django-esi 1.x and django-esi 2.x

### Changed

- Changed name from "Alliance Freight" to "Freight" to better reflect that this app works both for an alliance or a corporation

## [1.1.3] - 2020-06-30

### Changed

- Update to Font Awesome v5. Thanks to Peter Pfeufer for your contribution!

## [1.1.2] - 2020-06-10

### Changed

- Enabled Black formatting for the whole codebase

### Fixed

- ESI timeout defaults

## [1.1.1] - 2020-05-28

### Changed

- Updated dependency for django-esi to exclude 2.0
- Added timeout to ESI requests

## [1.1.0] - 2020-04-19

**Custom app name**

### Added

- The default app name ("Freight") as shown in the sidebar and title can now be customized with a setting

### Fixed

- Customer notification now also works for failed contracts without acceptor
- Price per volume modifier no longer fails when there is no contract handler
- HTML not parsed in info box ([#30](https://gitlab.com/ErikKalkoken/aa-freight/issues/21))
- New attempt to reduce the memory leaks in celery workers

### Changed

- Dropped support for Python 3.5. Now requires Python 3.6+ to install.

## [1.0.0] - 2020-04-09

**Default pricing**

### Added

- You can now set a default pricing, which will be preselected in the calculator
- Contract sync status now shown as traffic light on admin site (under Contract Handler)
- New setting FREIGHT_CONTRACT_SYNC_GRACE_MINUTES determines after what time a delayed sync is reported as error

### Fixed

- Sorting on statistics page is now the same for all panels (by contract then rewards)

## [0.13.1] - 2020-02-02

If you already have Pricings for both direction of the same route please make sure to set both to non-bidirectional. Otherwise those Pricings will not work probable.

### Changed

- It is now possible again to save changes to a Pricing if another bi-directional Pricing for the same route already exists. This is necessary to set both existing Pricing definitions to non-bidirectional.

## [0.13.0] - 2020-01-31

**Uni-directional pricings**

### Added

- It is now also possible to define different pricings for either direction of a route. However, pricings will remain bidirectional by default. ([#21](https://gitlab.com/ErikKalkoken/aa-freight/issues/21))

### Fixed

- It's no longer possible to create a 2nd bidirectional pricing for the same route

## [0.12.5] - 2020-01-30

### Fixed

- The pricing matched to a contract is no longer random if two pricings exist for the same route. It will now always pick the first pricing that was created.<br>**Note:** Freight current does officially not support defining individual pricings for each directions of a route.

## [0.12.4] - 2020-01-27

### Added

- Added direct links to contract list views in Discord notifications

## [0.12.3] - 2019-12-19

### Changed

- Improved error handling for contract sync. A single failed contract will no longer fail the hinder other contracts from being synced. ([#27](https://gitlab.com/ErikKalkoken/aa-freight/issues/27))

## [0.12.2] - 2019-12-17

### Changed

- Input for volume and collateral changed to exact figures ([#18](https://gitlab.com/ErikKalkoken/aa-freight/issues/18))

- Volume on notification now also shown as exact figures. ISK figures shown in M format.

## [0.12.1] - 2019-12-16

### Added

- Show notification status for each contract on admin page

- Show "days to expire" in addition to expiration date in calculator / "Your Contract" panel ([#26](https://gitlab.com/ErikKalkoken/aa-freight/issues/26))

### Changed

- Will no longer show deleted contracts on "My Contracts" page. ([#25](https://gitlab.com/ErikKalkoken/aa-freight/issues/25))

- Will no longer show empty "Accepted By" and "Accepted On" fields on notifications

- Some data models on admin page are not read only or hidden completely to prevent accidental data corruption

## [0.12.0] - 2019-12-15

**Statistics**

### Added

- Statistics for pilot corporations, which also include contracts that are accepted by corporations
- Added section explaining in details how the "contract check" feature works

### Changed

- Renamed "Price Check" to "Contract Check", which better expresses that not only the reward, but also volume and collateral are checked for compliance
- Updated "pricing details" and "your contracts" info boxes on the calculator to better reflect that routes are bidirectional

### Fixed

- Pilots and Customer count was mixed up on the statistics page for routes.

## [0.11.4] - 2019-12-14

### Fixed

- Contract sync fails when contract was accepted by corp instead of a character. (permanent fix) ([#22](https://gitlab.com/ErikKalkoken/aa-freight/issues/22))

## [0.11.3] - 2019-12-14

### Fixed

- Contract sync fails when contract was accepted by corp instead of a character. (temporary fix) ([#22](https://gitlab.com/ErikKalkoken/aa-freight/issues/22))

## [0.11.2] - 2019-12-12

### Added

- Improve test coverage

### Fixed

- Entering 0 collateral or 0 volume is treated by the calculator as not having entered any value ([#17](https://gitlab.com/ErikKalkoken/aa-freight/issues/17))

## [0.11.1] - 2019-12-11

### Added

- Will no longer send out customer notifications for outdated contracts, e.g. when first turning on the customer notification feature. See also related new setting `FREIGHT_HOURS_UNTIL_STALE_STATUS`. ([#19](https://gitlab.com/ErikKalkoken/aa-freight/issues/19))

## [0.11.0] - 2019-12-10

**Global pricing components**

### Added

- Add global "price per volume" optional modifier ([#15](https://gitlab.com/ErikKalkoken/aa-freight/issues/15))

## [0.10.1] - 2019-12-07

### Added

- Add new testing tools (tox) to enable CI

- Improve error handling when posting messages on Discord

## [0.10.0] - 2019-12-06

**Customer notifications**

### Added

- New feature: Automatically sends out messages to contract issuer informing him about the developing status of his contract (optional)

### Changed

- Will no longer show expired contracts on "Active Contracts" page

### Fixed

- Localization fix: ([#18](https://gitlab.com/ErikKalkoken/aa-freight/issues/18))

## [0.9.3] - 2019-12-06

### Fixed

- On the calculator fields for volume and collateral would still show if a related pricing element was set to 0 ([#17](https://gitlab.com/ErikKalkoken/aa-freight/issues/17))

## [0.9.2] - 2019-11-23

### Added

- Add setting to enable full location names on calculator route down  ([#14](https://gitlab.com/ErikKalkoken/aa-freight/issues/14))

## [0.9.1] - 2019-11-22

### Added

- Show full location names of start and destination for selected route in calculator ([#14](https://gitlab.com/ErikKalkoken/aa-freight/issues/14))

## [0.9.0] - 2019-11-12

**Custom mentions**

### Changed

- Renamed setting `FREIGHT_DISCORD_PING_TYPE` to `FREIGHT_DISCORD_MENTIONS`. This setting now accepts any kind of mentions incl. role and user mentions. Make sure to update your `local.py` accordingly if you use pings! ([#13](https://gitlab.com/ErikKalkoken/aa-freight/issues/13))

- Now using a different library for communicating with Discord

### Added

## [0.8.0] - 2019-11-08

**Corporation public operation mode**

### Added

- Add new operation mode "Corporation public" for processing any courier contract assigned to a corporation ([#3](https://gitlab.com/ErikKalkoken/aa-freight/issues/3))
- New statistics page showing KPIs for routes, pilots and customers ([#7](https://gitlab.com/ErikKalkoken/aa-freight/issues/7))
- Improved view on mobile devices for all tables

### Fixed

- List of routes in drop-down on calculator now sorted alphabetically by its name ([#11](https://gitlab.com/ErikKalkoken/aa-freight/issues/11))
- Technical update to model to fix "missing migrations" ([#12](https://gitlab.com/ErikKalkoken/aa-freight/issues/12))

## [0.7.0] - 2019-11-04

### Added

- New operation mode: "Corporation in my Alliance": all contracts assigned to designated corporation within the alliance by an alliance member

## [0.6.0] - 2019-11-01

### Added

- Automatic branding of webhook can not be turned off with a new setting ([#10](https://gitlab.com/ErikKalkoken/aa-freight/issues/10))

### Changed

- Removed FREIGHT_DISCORD_AVATAR_URL setting, since the same effect can not now be achieved by turning off branding

## [0.5.2] - 2019-10-30

### Changed

- Users can now see all active contracts even if they don't have a character in the organization running the freight service (they still need to respective permission though)
- Current operation mode no longer shown on admin page

### Fixed

- Contracts from non corp characters are no longer processes for my_corporation mode

## [0.5.1] - 2019-10-30

You need to run migrations when updating to this version.

### Fixed

- Trying to create a new route leads to an internal error 500: (`MySQLdb._exceptions.OperationalError: (1366, "Incorrect string value`...)

## [0.5.0] - 2019-10-30

You need to run migrations when updating to this version.

**IMPORTANT**

You need to delete your current contract handler **before** starting migrations or they will fail !! You can delete the contract handler on the admin page.

In case you already ran into this issue you can fix this by rewinding migrations to 0004, delete the contract handler and then re-run migrations. The command for rewinding migrations to 004 is: `python manage.py migrate freight 0004`.

### Added

- The new feature "operation mode" allows to configure which kind of contracts are processed by the app. Default mode is "My Alliance" for contracts available to members of your alliance only.
- New operation mode "My Corporation" for contracts available to members of your corporation only. ([#3](https://gitlab.com/ErikKalkoken/aa-freight/issues/3))
- Notes / comments on contracts are now visible in the contracts list

## [0.4.0] - 2019-10-28

"Run migrations" and "collect static" needs to be run when updating to this version.

### Added

- Contract List: Contracts can now be filtered by route, status or issuer
- Contract List: Color coding for contracts based on high level status: open, in progress, failed, completed
- Changelog file

### Changed

- Routes now more clearly shown as bi-directional to users ([#8](https://gitlab.com/ErikKalkoken/aa-freight/issues/8))
- Technical update to data models

## [0.3.0] - 2019-10-27

### Added

- Add page to check status of own courier contracts ([#6](https://gitlab.com/ErikKalkoken/aa-freight/issues/6))

## [0.2.0] - 2019-10-27

### Added

- Calculator: Name of group that can accept contracts now shown ([#4](https://gitlab.com/ErikKalkoken/aa-freight/issues/4))
- Pricing: Routes can now have a fix price of 0 ISK ([#1](https://gitlab.com/ErikKalkoken/aa-freight/issues/1))

### Changed

- Calculator: Routes with just a base price will be shown as "Fix price" in calculator

- Calculator: Volume and/or collateral no longer shown if not needed for price calculation

### Fixed

- Calculator: Contracts with 0 ISK collateral now correctly displayed ([#2](https://gitlab.com/ErikKalkoken/aa-freight/issues/2))

## [0.1.5] - 2019-10-23

### Added

- Notifications: Ability to enable pinging of contract notifications with `@here` or `@everyone`

## [0.1.4] - 2019-10-22

### Fixed

- Contract sync aborted when acceptor was an Eve character unknown to AA
