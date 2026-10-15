Feature: Ett mejl som redan ligger i papperskorgen raderas aldrig permanent av misstag
  Som en MCP-klient
  vill jag att delete_email och move_email till Trash lämnar ett mejl orört när det redan ligger i Trash,
  eftersom Bridge annars raderar det permanent. Ett mejl till sig själv är ETT Proton-mejl som syns i både
  INBOX och Sent, och Bridges Sent-vy visar det i 20–40 s efter att det flyttats till Trash.

  Scenario: Sent-kopian av ett mejl till sig själv tas bort strax efter INBOX-kopian
    Given att mejlet "<sjalv@x>" till mig själv ligger i "INBOX" med UID "10" och i "Sent" med UID "20"
    When jag tar bort mejlet med UID "10" i "INBOX"
    And jag tar bort mejlet med UID "20" i "Sent"
    Then ska verktyget svara att UID "20" lyckades med förklaringen "ligger redan i papperskorgen"
    And ska mejlet "<sjalv@x>" fortfarande ligga i "Trash"
    And ska Bridge inte ha fått någon flytt från "Sent"

  Scenario: Massradering där ett av mejlen redan ligger i papperskorgen
    Given att mejlet "<sjalv@x>" till mig själv ligger i "INBOX" med UID "10" och i "Sent" med UID "20"
    And att mejlet "<annat@x>" ligger i "Sent" med UID "21"
    When jag tar bort mejlet med UID "10" i "INBOX"
    And jag tar bort UID-listan "20, 21" i "Sent"
    Then ska massvaret ha UID "20, 21" som lyckade och en förklaring som nämner UID "20"
    And ska mejlet "<sjalv@x>" fortfarande ligga i "Trash"
    And ska mejlet "<annat@x>" ligga i "Trash"
    And ska Bridge ha fått exakt en sökning i "Trash"

  Scenario: move_email till Trash av ett mejl som redan ligger där
    Given att mejlet "<sjalv@x>" till mig själv ligger i "INBOX" med UID "10" och i "Sent" med UID "20"
    When jag tar bort mejlet med UID "10" i "INBOX"
    And jag flyttar mejlet med UID "20" i "Sent" till "Trash"
    Then ska verktyget svara att UID "20" lyckades med förklaringen "ligger redan i papperskorgen"
    And ska mejlet "<sjalv@x>" fortfarande ligga i "Trash"

  Scenario: Ett vanligt mejl flyttas till papperskorgen som förut
    Given att mejlet "<annat@x>" ligger i "Sent" med UID "21"
    When jag tar bort mejlet med UID "21" i "Sent"
    Then ska verktyget svara True
    And ska mejlet "<annat@x>" ligga i "Trash"

  Scenario: Ett mejl utan Message-ID flyttas som förut
    Given att ett mejl utan Message-ID ligger i "INBOX" med UID "30"
    When jag tar bort mejlet med UID "30" i "INBOX"
    Then ska verktyget svara True
    And ska Bridge inte ha sökt i "Trash"
