// Copyright (c) 2024 SnowyKami Liteyuki Studio All Rights Reserved.


/**
 * @type {{
 *   results: Array<{
 *       abstracts: string,
 *       createdDt: string,
 *       endStaName: string,
 *       startStaName: string,
 *       isValid: boolean,
 *       needTimeScope: number,
 *       needTransferTimes: number,
 *       price: number,
 *       skipGenerateSequence: boolean,
 *       transferLines: string,
 *       transferLinesColor: string,
 *       transferStaDerict: string,
 *       transferStaNames: string,
 *   }>
 * }}
 */

const data = JSON.parse(document.getElementById("data").innerText);
const results = data["result"];
const route_template = document.importNode(document.getElementById("route-template").content, true)

results.forEach(
    (item, index) => {

    }
)



