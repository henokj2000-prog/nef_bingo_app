PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE players (
            user_id INTEGER PRIMARY KEY,
            username TEXT, full_name TEXT,
            balance REAL DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            total_won REAL DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            phone TEXT DEFAULT NULL,
            language TEXT DEFAULT "en",
            chat_id TEXT DEFAULT NULL
        , referred_by DEFAULT NULL, referral_code DEFAULT NULL, referral_bonus_earned DEFAULT NULL);
INSERT INTO players VALUES(-10,'hana_t','Hana Tesfaye',1000.0,0,0,0.0,0,NULL,'en',NULL,NULL,NULL,NULL);
INSERT INTO players VALUES(-9,'dawit_m','Dawit Mekonnen',1000.0,0,0,0.0,0,NULL,'en',NULL,NULL,NULL,NULL);
INSERT INTO players VALUES(-8,'meron_a','Meron Assefa',1000.0,0,0,0.0,0,NULL,'en',NULL,NULL,NULL,NULL);
INSERT INTO players VALUES(-7,'biruk_a','Biruk Alemu',1000.0,0,0,0.0,0,NULL,'en',NULL,NULL,NULL,NULL);
INSERT INTO players VALUES(-6,'tigist_d','Tigist Desta',1000.0,0,0,0.0,0,NULL,'en',NULL,NULL,NULL,NULL);
INSERT INTO players VALUES(-5,'emu_k','Emu Konjo',1000.0,0,0,0.0,0,NULL,'en',NULL,NULL,NULL,NULL);
INSERT INTO players VALUES(-4,'shime_g','Shime Gondar',1000.0,0,0,0.0,0,NULL,'en',NULL,NULL,NULL,NULL);
INSERT INTO players VALUES(-3,'aradaw_t','Aradaw Tade',1000.0,0,0,0.0,0,NULL,'en',NULL,NULL,NULL,NULL);
INSERT INTO players VALUES(-2,'yichilal','Yichilal',1000.0,0,0,0.0,0,NULL,'en',NULL,NULL,NULL,NULL);
INSERT INTO players VALUES(-1,'admasu_k','Admasu Kebe',1000.0,0,0,0.0,0,NULL,'en',NULL,NULL,NULL,NULL);
INSERT INTO players VALUES(99999,'user','Player',0.0,0,0,0.0,0,'09290010000','en',NULL,NULL,'DQS3CKBC',NULL);
CREATE TABLE games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stake INTEGER, status TEXT DEFAULT 'waiting',
            prize_pool REAL DEFAULT 0,
            drawn_balls TEXT DEFAULT '[]',
            winner_card_numbers TEXT DEFAULT '[]',
            created_at REAL, started_at REAL, finished_at REAL,
            cancelled INTEGER DEFAULT 0
        );
CREATE TABLE game_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER, user_id INTEGER,
            card_number INTEGER, card_data TEXT
        );
CREATE TABLE deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL,
            platform TEXT, tx_ref TEXT,
            status TEXT DEFAULT 'pending', created_at REAL
        );
CREATE TABLE withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL,
            platform TEXT, account_no TEXT,
            status TEXT DEFAULT 'pending', created_at REAL
        );
CREATE TABLE inquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, subject TEXT,
            message TEXT, status TEXT DEFAULT 'open', created_at REAL
        );
CREATE TABLE bonuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL,
            reason TEXT, admin_note TEXT, created_at REAL
        );
CREATE TABLE notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            created_at REAL NOT NULL,
            is_broadcast INTEGER DEFAULT 1
        );
CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
INSERT INTO settings VALUES('telebirr_number','0929 001 000');
INSERT INTO settings VALUES('cbe_number','1000061737212');
INSERT INTO settings VALUES('deposit_bonus_percent','0');
INSERT INTO settings VALUES('referral_commission_percent','5');
INSERT INTO settings VALUES('referral_bonus_amount','10');
INSERT INTO settings VALUES('owner_cut_percent','20');
INSERT INTO settings VALUES('max_balls_per_game','75');
INSERT INTO settings VALUES('bot_enabled','1');
INSERT INTO settings VALUES('bot_cards_per_game','1');
INSERT INTO settings VALUES('bot_min_players','2');
CREATE TABLE admins (
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'admin',
            added_by INTEGER,
            created_at REAL
        );
CREATE TABLE referral_codes (
            user_id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL
        );
INSERT INTO referral_codes VALUES(99999,'DQS3CKBC');
CREATE TABLE referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            created_at REAL
        );
CREATE TABLE referral_commissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            game_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at REAL,
            paid_at REAL
        );
CREATE TABLE referral_commissions_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            game_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            paid_at REAL,
            payment_week_start REAL,
            payment_week_end REAL
        );
CREATE UNIQUE INDEX idx_unique_phone ON players(phone);
COMMIT;
