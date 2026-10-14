Feature: Lägga till en etikett på ett mejl
  Som en MCP-klient
  vill jag kunna sätta en etikett på ett mejl
  utan att mejlet flyttas ur mappen där det ligger.

  Scenario: Etiketten läggs till med UID COPY och mejlet ligger kvar i Inkorgen
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    When jag lägger till etiketten "Kvitton" på UID "42" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID COPY" med "42 "Labels/Kvitton""
    And ska mejlet med Message-ID "<a@x>" ligga i "INBOX"
    And ska mejlet med Message-ID "<a@x>" ligga i "Labels/Kvitton"
    And ska Bridge inte ha fått "UID MOVE"

  Scenario: Etikettnamnet får anges med prefixet Labels/
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    When jag lägger till etiketten "Labels/Kvitton" på UID "42" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID COPY" med "42 "Labels/Kvitton""

  Scenario: En etikett som inte finns ger fel som hänvisar till create_folder
    Given att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    When jag lägger till etiketten "Saknas" på UID "42" i "INBOX"
    Then ska verktyget ge ett fel som nämner "create_folder("Labels/Saknas")"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Ett UID som inte finns i mappen ger fel i stället för "lyckades"
    Given att etiketten "Labels/Kvitton" finns
    When jag lägger till etiketten "Kvitton" på UID "99999" i "INBOX"
    Then ska verktyget ge ett fel som nämner "Inget meddelande med UID 99999 i INBOX"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Starred är ingen etikett utan stjärnmärkning
    Given att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    When jag lägger till etiketten "Starred" på UID "42" i "INBOX"
    Then ska verktyget ge ett fel som nämner "flag_email"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: En mapp är ingen etikett
    Given att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    When jag lägger till etiketten "Folders/Projekt" på UID "42" i "INBOX"
    Then ska verktyget ge ett fel som nämner "move_email"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Om Bridge nekar får klienten veta varför
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "42" och Message-ID "<a@x>" ligger i "INBOX"
    And att Bridge nekar COPY med "backend error"
    When jag lägger till etiketten "Kvitton" på UID "42" i "INBOX"
    Then ska verktyget ge ett fel som nämner "backend error"
