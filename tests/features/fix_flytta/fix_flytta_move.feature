Feature: Flytta ett mejl utan att röra andra mejl
  Som en MCP-klient
  vill jag kunna flytta ett enskilt mejl mellan mappar
  utan att andra mejl i mappen påverkas eller att något raderas av misstag.

  Scenario: Flytt till en mapp görs med UID MOVE och bara på det mejlet
    Given att mejlet med UID "42" ligger i "INBOX"
    When jag flyttar mejlet med UID "42" från "INBOX" till "Archive"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID MOVE" med "42 "Archive""
    And ska Bridge inte ha fått "EXPUNGE"
    And ska Bridge inte ha fått "UID STORE"

  # Att mejlet då ligger kvar i Inkorgen bygger på Bridges källkod (rapport-proton N2);
  # låtsas-Bridgen modellerar inte det, så scenariot kontrollerar bara kommandot.
  Scenario: Flytt till en etikett görs med UID MOVE och utan EXPUNGE
    Given att mejlet med UID "42" ligger i "INBOX"
    When jag flyttar mejlet med UID "42" från "INBOX" till "Labels/Kvitton"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID MOVE" med "42 "Labels/Kvitton""
    And ska Bridge inte ha fått "EXPUNGE"

  Scenario: Flytt till samma mapp avvisas eftersom Bridge då raderar mejlet i Trash
    Given att mejlet med UID "7" ligger i "Trash"
    When jag flyttar mejlet med UID "7" från "Trash" till "Trash"
    Then ska verktyget ge ett fel som nämner "samma mapp"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Flytt till papperskorgen från en etikett avvisas
    Given att mejlet med UID "7" ligger i "Starred"
    When jag flyttar mejlet med UID "7" från "Starred" till "Trash"
    Then ska verktyget ge ett fel som nämner "redan ligga i Trash"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Flytt från All Mail avvisas med en begriplig förklaring
    Given att mejlet med UID "7" ligger i "All Mail"
    When jag flyttar mejlet med UID "7" från "All Mail" till "Archive"
    Then ska verktyget ge ett fel som nämner "All Mail"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Ett UID som inte finns i källmappen ger fel i stället för "lyckades"
    When jag flyttar mejlet med UID "99999" från "INBOX" till "Archive"
    Then ska verktyget ge ett fel som nämner "Inget meddelande med UID 99999 i INBOX"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Om Bridge nekar flytten får klienten veta varför
    Given att mejlet med UID "42" ligger i "INBOX"
    And att Bridge nekar MOVE med "operation not allowed"
    When jag flyttar mejlet med UID "42" från "INBOX" till "Archive"
    Then ska verktyget ge ett fel som nämner "operation not allowed"
