# CHANGELOG

<!-- version list -->

## v1.27.0 (2026-07-16)

### Features

- Add public doctor-directory endpoint ([#56](https://github.com/mks-zakaria/sehaty-api/pull/56),
  [`e02ca49`](https://github.com/mks-zakaria/sehaty-api/commit/e02ca496202f32ee63fd78e9c7e52664d7848270))


## v1.26.0 (2026-07-15)

### Features

- Expose doctor slug in assistant's doctor list
  ([#54](https://github.com/mks-zakaria/sehaty-api/pull/54),
  [`725f65c`](https://github.com/mks-zakaria/sehaty-api/commit/725f65c917681b787ead5a9049e5853dba80e984))


## v1.25.0 (2026-07-15)

### Features

- Add prescription-template endpoints (list, create, delete)
  ([#52](https://github.com/mks-zakaria/sehaty-api/pull/52),
  [`c0abc5f`](https://github.com/mks-zakaria/sehaty-api/commit/c0abc5f081b8023989bd1ac32d98e1ec2fa9185e))


## v1.24.0 (2026-07-15)

### Features

- Add doctor dashboard endpoint (today, to-confirm, upcoming, patients, next appointment)
  ([#50](https://github.com/mks-zakaria/sehaty-api/pull/50),
  [`d374ab9`](https://github.com/mks-zakaria/sehaty-api/commit/d374ab9f96994a0accca8247bd344f283d6564a1))


## v1.23.0 (2026-07-15)

### Features

- Add admin run-reminders endpoint (cron-triggerable appointment reminders)
  ([#48](https://github.com/mks-zakaria/sehaty-api/pull/48),
  [`728cc9f`](https://github.com/mks-zakaria/sehaty-api/commit/728cc9f1a03228bbdc9e9ad395fe6632d6cec5e7))


## v1.22.0 (2026-07-15)

### Features

- Expose doctor_slug on patient appointments
  ([#46](https://github.com/mks-zakaria/sehaty-api/pull/46),
  [`f596bef`](https://github.com/mks-zakaria/sehaty-api/commit/f596bef6778996ea87f1670375fbd039996c6cb6))


## v1.21.0 (2026-07-15)

### Features

- Add patient and doctor/assistant appointment reschedule endpoints
  ([#44](https://github.com/mks-zakaria/sehaty-api/pull/44),
  [`cebe723`](https://github.com/mks-zakaria/sehaty-api/commit/cebe723b3c0f6ea1a9d41014b01c1978e70001fb))


## v1.20.0 (2026-07-15)

### Features

- Add availability-exceptions endpoints and timezone in doctor profile
  ([#42](https://github.com/mks-zakaria/sehaty-api/pull/42),
  [`e22d638`](https://github.com/mks-zakaria/sehaty-api/commit/e22d638211298ecb3b1ddb13db2a1cd3d10c4b94))


## v1.19.0 (2026-07-15)

### Features

- Add doctor name to patient appointments + patient prescription detail endpoint
  ([#40](https://github.com/mks-zakaria/sehaty-api/pull/40),
  [`5f08f3c`](https://github.com/mks-zakaria/sehaty-api/commit/5f08f3ceb86e6a9b5f4325b11aea6ecce764d322))


## v1.18.0 (2026-07-15)

### Features

- Add doctor/assistant appointment grid + confirm-on-behalf endpoints
  ([#38](https://github.com/mks-zakaria/sehaty-api/pull/38),
  [`6d8eef6`](https://github.com/mks-zakaria/sehaty-api/commit/6d8eef6988362490ee1723ddeb690cc59cb0ac93))


## v1.17.0 (2026-07-15)

### Features

- Add assistant management endpoints and acting-doctor dependency
  ([#36](https://github.com/mks-zakaria/sehaty-api/pull/36),
  [`b4acac9`](https://github.com/mks-zakaria/sehaty-api/commit/b4acac981b641ec105c494c9d7d1f4f2a082ee8f))


## v1.16.0 (2026-07-15)

### Features

- Add clinical API (practice profiles, prescriptions, diagnoses, patient feedback)
  ([#34](https://github.com/mks-zakaria/sehaty-api/pull/34),
  [`fad7953`](https://github.com/mks-zakaria/sehaty-api/commit/fad79533e8873d3d805d03d3415154c33dc3ae16))


## v1.15.0 (2026-07-15)

### Features

- Add doctor patient-register endpoints (list, detail+history, add walk-in, update)
  ([#32](https://github.com/mks-zakaria/sehaty-api/pull/32),
  [`f61c68b`](https://github.com/mks-zakaria/sehaty-api/commit/f61c68bf00ade43b6d627dbc47be217718ba0b0b))


## v1.14.0 (2026-07-14)

### Features

- Add admin users and subscriptions listing endpoints
  ([#30](https://github.com/mks-zakaria/sehaty-api/pull/30),
  [`73b3cc5`](https://github.com/mks-zakaria/sehaty-api/commit/73b3cc5205a6dead150a74e1b7170f5a5235239c))


## v1.13.0 (2026-07-14)

### Features

- Add admin ranking-weights and feature-flags endpoints
  ([#28](https://github.com/mks-zakaria/sehaty-api/pull/28),
  [`1e84b15`](https://github.com/mks-zakaria/sehaty-api/commit/1e84b150fab451a20c70df7babba707516ba0024))


## v1.12.0 (2026-07-14)

### Features

- Add admin reporting endpoints + year-end CSV accounting export
  ([#26](https://github.com/mks-zakaria/sehaty-api/pull/26),
  [`2f5d601`](https://github.com/mks-zakaria/sehaty-api/commit/2f5d601aa9c6d86b42044c4b1ebac48ecc024770))


## v1.11.0 (2026-07-14)

### Features

- Add notifications endpoints (feed, unread count, mark read)
  ([#24](https://github.com/mks-zakaria/sehaty-api/pull/24),
  [`06830fb`](https://github.com/mks-zakaria/sehaty-api/commit/06830fbd5ed827a6b8bc8716bd7ee1982b485099))


## v1.10.0 (2026-07-14)

### Features

- Add referral endpoints + capture referral code at doctor registration
  ([#22](https://github.com/mks-zakaria/sehaty-api/pull/22),
  [`7c43a82`](https://github.com/mks-zakaria/sehaty-api/commit/7c43a82d8f0ff450bd4331a23824e779a47a6987))


## v1.9.0 (2026-07-14)

### Features

- Add cash-billing endpoints (plans, subscription, cash payments, dunning)
  ([#20](https://github.com/mks-zakaria/sehaty-api/pull/20),
  [`130f94f`](https://github.com/mks-zakaria/sehaty-api/commit/130f94fc034b9a4f3756af8c62c94458fdb538a6))


## v1.8.0 (2026-07-14)

### Features

- Add reviews API (create, reply, flag, public list, moderation)
  ([#18](https://github.com/mks-zakaria/sehaty-api/pull/18),
  [`0da8e64`](https://github.com/mks-zakaria/sehaty-api/commit/0da8e646401cf1c255b50106d77bb39a91a4e341))


## v1.7.0 (2026-07-14)

### Features

- Expose doctor id in public doctor endpoint
  ([#16](https://github.com/mks-zakaria/sehaty-api/pull/16),
  [`75d1754`](https://github.com/mks-zakaria/sehaty-api/commit/75d17546dc22f7123df54417aac8ae6335210b64))


## v1.6.0 (2026-07-14)

### Features

- Add slug-keyed public slots endpoint ([#14](https://github.com/mks-zakaria/sehaty-api/pull/14),
  [`1dfa9c4`](https://github.com/mks-zakaria/sehaty-api/commit/1dfa9c47064fb421756b1b2591aed176d43177e1))


## v1.5.0 (2026-07-14)

### Features

- Add booking API (availability, slots, appointments)
  ([#12](https://github.com/mks-zakaria/sehaty-api/pull/12),
  [`2e3421e`](https://github.com/mks-zakaria/sehaty-api/commit/2e3421e3884e4e3c69c5c59990095ffc5d2f3b7e))


## v1.4.0 (2026-07-14)

### Features

- Add doctor search API (nearest by specialty, ranked)
  ([#10](https://github.com/mks-zakaria/sehaty-api/pull/10),
  [`f7c8241`](https://github.com/mks-zakaria/sehaty-api/commit/f7c8241355d88f6bd38a9f5b593dea1e41b4415f))


## v1.3.0 (2026-07-14)

### Features

- Add doctor profile API (upsert, public page, specialties)
  ([#8](https://github.com/mks-zakaria/sehaty-api/pull/8),
  [`9321194`](https://github.com/mks-zakaria/sehaty-api/commit/9321194f70d6355d8cc194f35140e00bbfce2574))


## v1.2.0 (2026-07-14)

### Features

- Add accreditation API (admin accredit/revoke/list)
  ([#6](https://github.com/mks-zakaria/sehaty-api/pull/6),
  [`0cd3ceb`](https://github.com/mks-zakaria/sehaty-api/commit/0cd3ceb08cc50d93422e0a88f4b1389cf167bc38))


## v1.1.0 (2026-07-14)

### Features

- Add auth API (register, login, OTP, refresh, me)
  ([#4](https://github.com/mks-zakaria/sehaty-api/pull/4),
  [`a958057`](https://github.com/mks-zakaria/sehaty-api/commit/a958057606377f48e2cccb41261138c05ae28310))


## v1.0.0 (2026-07-14)

- Initial Release
