Feature: Flytt till Starred hänvisar till flag_email
  Som en MCP-klient
  vill jag få veta vilket verktyg som stjärnmärker
  när jag försöker flytta ett mejl till Starred.

  Scenario: Flytt av ett mejl till Starred avvisas med hänvisning till flag_email
    Given att mejlen med UID "3" ligger i "INBOX"
    When jag flyttar mejlet med UID "3" från "INBOX" till "Starred"
    Then ska verktyget ge ett fel som nämner "flag_email"
    And ska Bridge inte ha fått något kommando

  Scenario: Flytt av flera mejl till Starred avvisas likadant
    Given att mejlen med UID "3, 4" ligger i "INBOX"
    When jag flyttar UID-listan "3, 4" från "INBOX" till "Starred"
    Then ska verktyget ge ett fel som nämner "flag_email"
    And ska Bridge inte ha fått något kommando
