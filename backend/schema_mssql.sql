-- SQL Server 2019+. Called automatically by init_db.py in FinPredictAI.
-- Safe to run again: existing tables and transactions are preserved.
-- Money is stored in integer tiyn (1 KZT = 100 tiyn), matching the Python API.
SET XACT_ABORT ON;
SET NOCOUNT ON;
BEGIN TRANSACTION;
DECLARE @SchemaLock INT;
EXEC @SchemaLock = sys.sp_getapplock
    @Resource = N'FinPredictAI.schema.v1', @LockMode = 'Exclusive',
    @LockOwner = 'Transaction', @LockTimeout = 15000;
IF @SchemaLock < 0
    THROW 50001, N'Не удалось получить блокировку инициализации схемы.', 1;
IF OBJECT_ID(N'dbo.Accounts', N'U') IS NULL
BEGIN
CREATE TABLE dbo.Accounts (
    Id NVARCHAR(64) NOT NULL PRIMARY KEY,
    Name NVARCHAR(120) NOT NULL,
    Opening BIGINT NOT NULL,
    Number NVARCHAR(32) NOT NULL,
    Currency CHAR(3) NOT NULL CONSTRAINT DF_Accounts_Currency DEFAULT 'KZT'
);
END;
IF COL_LENGTH('dbo.Accounts','AsOfDate') IS NULL
    ALTER TABLE dbo.Accounts ADD AsOfDate DATE NULL;
IF COL_LENGTH('dbo.Accounts','HistoryStartDate') IS NULL
    ALTER TABLE dbo.Accounts ADD HistoryStartDate DATE NULL;
IF COL_LENGTH('dbo.Accounts','BankHash') IS NULL
    ALTER TABLE dbo.Accounts ADD BankHash CHAR(64) NULL;
IF OBJECT_ID(N'dbo.Categories', N'U') IS NULL
BEGIN
CREATE TABLE dbo.Categories (
    Id VARCHAR(32) NOT NULL PRIMARY KEY,
    Name NVARCHAR(120) NOT NULL
);
END;
INSERT INTO dbo.Categories (Id,Name)
SELECT categories.Id, categories.Name FROM (VALUES
('housing',N'Жильё'),('food',N'Продукты'),('cafe',N'Кафе и рестораны'),
('shopping',N'Покупки'),('transport',N'Транспорт'),('services',N'Подписки и услуги'),
('health',N'Здоровье'),('leisure',N'Развлечения'),('salary',N'Зарплата'),
('freelance',N'Подработка'),('other',N'Другое')
) AS categories(Id,Name)
WHERE NOT EXISTS (SELECT 1 FROM dbo.Categories AS existing WHERE existing.Id = categories.Id);
IF OBJECT_ID(N'dbo.Transactions', N'U') IS NULL
BEGIN
CREATE TABLE dbo.Transactions (
    Id NVARCHAR(64) NOT NULL PRIMARY KEY,
    AccountId NVARCHAR(64) NOT NULL,
    Date DATE NOT NULL,
    Description NVARCHAR(120) NOT NULL,
    Category VARCHAR(32) NOT NULL,
    Type VARCHAR(7) NOT NULL,
    Amount BIGINT NOT NULL,
    Recurring BIT NOT NULL CONSTRAINT DF_Transactions_Recurring DEFAULT 0,
    CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_Transactions_CreatedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_Transactions_Accounts FOREIGN KEY (AccountId) REFERENCES dbo.Accounts(Id),
    CONSTRAINT FK_Transactions_Categories FOREIGN KEY (Category) REFERENCES dbo.Categories(Id),
    CONSTRAINT CK_Transactions_Amount CHECK (Amount > 0),
    CONSTRAINT CK_Transactions_Type CHECK (Type IN ('income','expense'))
);
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'IX_Transactions_AccountDate'
               AND object_id=OBJECT_ID(N'dbo.Transactions'))
CREATE INDEX IX_Transactions_AccountDate ON dbo.Transactions(AccountId,Date DESC);
IF OBJECT_ID(N'dbo.Users', N'U') IS NULL
BEGIN
CREATE TABLE dbo.Users (
 Id NVARCHAR(64) NOT NULL PRIMARY KEY,
 Name NVARCHAR(120) NOT NULL,
 Email NVARCHAR(254) NOT NULL CONSTRAINT UQ_Users_Email UNIQUE,
 PasswordHash NVARCHAR(256) NOT NULL,
 AccountId NVARCHAR(64) NOT NULL CONSTRAINT UQ_Users_Account UNIQUE,
 CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_Users_Created DEFAULT SYSUTCDATETIME(),
 CONSTRAINT FK_Users_Accounts FOREIGN KEY(AccountId) REFERENCES dbo.Accounts(Id)
);
END;
IF OBJECT_ID(N'dbo.AuthSessions', N'U') IS NULL
BEGIN
CREATE TABLE dbo.AuthSessions (
 TokenHash CHAR(64) NOT NULL PRIMARY KEY,
 UserId NVARCHAR(64) NOT NULL,
 ExpiresAt DATETIME2 NOT NULL,
 CONSTRAINT FK_AuthSessions_Users FOREIGN KEY(UserId) REFERENCES dbo.Users(Id)
);
CREATE INDEX IX_AuthSessions_Expiry ON dbo.AuthSessions(ExpiresAt);
END;
IF COL_LENGTH('dbo.Users','Role') IS NULL
    ALTER TABLE dbo.Users ADD Role VARCHAR(8) NOT NULL CONSTRAINT DF_Users_Role DEFAULT 'user' CONSTRAINT CK_Users_Role CHECK (Role IN ('user','admin'));
IF OBJECT_ID(N'dbo.UserProfiles', N'U') IS NULL
BEGIN
CREATE TABLE dbo.UserProfiles (
 UserId NVARCHAR(64) NOT NULL PRIMARY KEY,
 City NVARCHAR(80) NOT NULL,
 Age INT NOT NULL CONSTRAINT CK_Profiles_Age CHECK (Age BETWEEN 18 AND 100),
 Occupation NVARCHAR(80) NOT NULL,
 Segment VARCHAR(20) NOT NULL,
 MonthlyIncome BIGINT NOT NULL,
 DemoSourceId VARCHAR(32) NULL CONSTRAINT UQ_Profiles_Source UNIQUE,
 CONSTRAINT FK_Profiles_Users FOREIGN KEY(UserId) REFERENCES dbo.Users(Id)
);
END;

-- Membership extension: repeat-safe migration; primary accounts are preserved.
IF OBJECT_ID(N'dbo.UserAccounts', N'U') IS NULL
BEGIN
CREATE TABLE dbo.UserAccounts (
 UserId NVARCHAR(64) NOT NULL,
 AccountId NVARCHAR(64) NOT NULL CONSTRAINT UQ_UserAccounts_Account UNIQUE,
 CONSTRAINT PK_UserAccounts PRIMARY KEY(UserId,AccountId),
 CONSTRAINT FK_UserAccounts_User FOREIGN KEY(UserId) REFERENCES dbo.Users(Id),
 CONSTRAINT FK_UserAccounts_Account FOREIGN KEY(AccountId) REFERENCES dbo.Accounts(Id)
);
END;
INSERT INTO dbo.UserAccounts(UserId,AccountId)
SELECT u.Id,u.AccountId FROM dbo.Users u
WHERE NOT EXISTS(SELECT 1 FROM dbo.UserAccounts a WHERE a.AccountId=u.AccountId);
IF OBJECT_ID(N'dbo.Subscriptions', N'U') IS NULL
BEGIN
CREATE TABLE dbo.Subscriptions (
 UserId NVARCHAR(64) NOT NULL PRIMARY KEY,
 ExpiresAt DATETIME2 NOT NULL,
 AutoRenew BIT NOT NULL DEFAULT 0,
 Price BIGINT NOT NULL DEFAULT 199000,
 Mode VARCHAR(8) NOT NULL DEFAULT 'demo' CHECK(Mode='demo'),
 CONSTRAINT FK_Subscriptions_User FOREIGN KEY(UserId) REFERENCES dbo.Users(Id)
);
END;
IF OBJECT_ID(N'dbo.Goals', N'U') IS NULL
BEGIN
CREATE TABLE dbo.Goals (
 Id NVARCHAR(64) NOT NULL PRIMARY KEY,
 UserId NVARCHAR(64) NOT NULL,
 Name NVARCHAR(120) NOT NULL,
 Target BIGINT NOT NULL CHECK(Target>0),
 Saved BIGINT NOT NULL CHECK(Saved>=0),
 Deadline DATE NOT NULL,
 CHECK(Saved<=Target),
 CONSTRAINT FK_Goals_User FOREIGN KEY(UserId) REFERENCES dbo.Users(Id)
);
END;
IF OBJECT_ID(N'dbo.StatementPreviews', N'U') IS NULL
BEGIN
CREATE TABLE dbo.StatementPreviews (
 Id CHAR(64) NOT NULL PRIMARY KEY,
 UserId NVARCHAR(64) NOT NULL,
 AccountId NVARCHAR(64) NOT NULL,
 RowsJson NVARCHAR(MAX) NOT NULL,
 ExpiresAt DATETIME2 NOT NULL,
 CONSTRAINT FK_StatementPreviews_User FOREIGN KEY(UserId) REFERENCES dbo.Users(Id),
 CONSTRAINT FK_StatementPreviews_Account FOREIGN KEY(AccountId) REFERENCES dbo.Accounts(Id)
);
CREATE INDEX IX_StatementPreviews_Expiry ON dbo.StatementPreviews(ExpiresAt);
END;

COMMIT;
GO
