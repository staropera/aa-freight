# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased] - yyyy-mm-dd

Here we write notes for upcoming releases.

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
