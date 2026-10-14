Feature: Starred är inget mål för move_email
  Som användare av move_email
  vill jag inte förlora ett mejl ur Inkorgen när jag försöker stjärnmärka det,
  eftersom Bridge räknar Starred som en systemmapp och tar bort mejlet ur källmappen.

  Scenario: Flytt till Starred avvisas med en hänvisning till \Flagged
    Given att mejlet med UID "3" ligger i "INBOX"
    When jag flyttar mejlet med UID "3" från "INBOX" till "Starred"
    Then ska verktyget ge ett fel som nämner "\Flagged"
    And ska Bridge inte ha fått något kommando

  Scenario: Skiftläget spelar ingen roll
    Given att mejlet med UID "3" ligger i "Archive"
    When jag flyttar mejlet med UID "3" från "Archive" till "starred"
    Then ska verktyget ge ett fel som nämner "Starred"
    And ska Bridge inte ha fått något kommando

  Scenario: Flytt från Starred till en mapp fungerar som förut
    Given att mejlet med UID "3" ligger i "Starred"
    When jag flyttar mejlet med UID "3" från "Starred" till "Archive"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "UID MOVE" med "3 "Archive""
