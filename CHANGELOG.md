# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased] - yyyy-mm-dd

Here we write notes for upcoming releases.

### Added
### Changed
### Fixed

## [0.5.0] - 2019-10-30

"Run migrations" needs to be run when updating to this version.

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