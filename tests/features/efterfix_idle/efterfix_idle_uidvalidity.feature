Feature: Bevakningen säger till när Bridge har numrerat om en mapp
  Som modell som håller koll på nya mejl
  vill jag få veta när Bridge har bytt UIDVALIDITY medan bevakningen var nere
  och ändå få se de mejl som kom under avbrottet
  så att inget nytt mejl försvinner tyst.

  Efter ett nytt UIDVALIDITY gäller inga gamla UID:n. Bevakningen letar
  därför fram mejl som kommit sedan den senast var i fas med Bridge efter
  ankomsttid (INTERNALDATE), och hoppar över dem den redan har rapporterat
  (samma Message-ID).

  Background:
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3
    And att servern bevakar INBOX och försöker igen efter 0.05 sekunder
    And att check_new_emails har anropats för INBOX

  Scenario: check_new_emails visar mejlen som kom under avbrottet och säger att UIDVALIDITY ändrats
    When Bridge är nere en stund, numrerar om INBOX och mejl med ämnena "Under 1,Under 2" kommer under tiden
    And bevakningen har återanslutit
    And jag anropar check_new_emails för INBOX
    Then ska svaret innehålla mejlen med ämnena "Under 2,Under 1"
    And ska anteckningen nämna "UIDVALIDITY"
    And ska anteckningen nämna "list_emails"

  Scenario: Anteckningen om UIDVALIDITY kommer bara en gång
    When Bridge är nere en stund, numrerar om INBOX och mejl med ämnena "Under 1" kommer under tiden
    And bevakningen har återanslutit
    And jag anropar check_new_emails för INBOX
    And jag anropar check_new_emails för INBOX
    Then ska svaret inte innehålla några mejl
    And ska svaret inte ha någon anteckning

  Scenario: Ett mejl som redan visats före avbrottet visas inte igen
    Given att ett mejl med ämnet "Före" har kommit och visats av check_new_emails
    When Bridge är nere en stund, numrerar om INBOX och mejl med ämnena "Under 1" kommer under tiden
    And bevakningen har återanslutit
    And jag anropar check_new_emails för INBOX
    Then ska svaret innehålla mejlen med ämnena "Under 1"

  Scenario: Ett mejl som kommer efter återanslutningen visas tillsammans med dem från avbrottet
    When Bridge är nere en stund, numrerar om INBOX och mejl med ämnena "Under 1" kommer under tiden
    And bevakningen har återanslutit
    And ett mejl med ämnet "Efter" kommer till INBOX och bevakningen har sett det
    And jag anropar check_new_emails för INBOX
    Then ska svaret innehålla mejlen med ämnena "Efter,Under 1"
    When ett mejl med ämnet "Sedan" kommer till INBOX och bevakningen har sett det
    And jag anropar check_new_emails för INBOX
    Then ska svaret innehålla mejlen med ämnena "Sedan"

  Scenario: wait_for_new_email säger också att UIDVALIDITY ändrats
    When Bridge är nere en stund och numrerar om INBOX
    And bevakningen har återanslutit
    And jag väntar på nya mejl i INBOX i högst 1 sekunder
    Then ska svaret inte innehålla några mejl
    And ska anteckningen nämna "UIDVALIDITY"
